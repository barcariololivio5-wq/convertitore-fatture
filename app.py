import streamlit as st
from google import genai
from google.genai import types
import json
from pydantic import BaseModel, Field
import pandas as pd
import io
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import time

# Schema dati per l'estrazione intelligente
class DatiFatturaEstera(BaseModel):
    fornitore: str = Field(description="Ragione sociale o nome dell'azienda che ha emesso la fattura")
    identificativo_fiscale_fornitore: str = Field(description="Partita IVA, VAT ID o Tax ID del fornitore senza spazi")
    indirizzo_fornitore: str = Field(description="Indirizzo completo del fornitore")
    paese_provenienza: str = Field(description="Codice ISO a 2 lettere del Paese del fornitore (es. US, IE, GB, FR, DE)")
    is_paese_ue: bool = Field(description="Vero se il paese fa parte dell'Unione Europea, Falso se Extra-UE")
    data_documento: str = Field(description="Data della fattura nel formato YYYY-MM-DD")
    valuta_originale: str = Field(description="Codice ISO a 3 lettere della valuta (es. USD, GBP, EUR)")
    imponibile_valuta_originale: float = Field(description="Importo imponibile totale")
    categoria_costo_suggerita: str = Field(description="Categoria tra: 'Software SaaS', 'Hosting/Cloud', 'Pubblicità/Marketing', 'Beni strumentali', 'Consulenza'")
    codice_autofattura_sdi: str = Field(description="Codice SDI richiesto: 'TD17' (servizi esteri), 'TD18' (beni UE), 'TD19' (beni ex art.17 c.2).")

# --- FUNZIONE DI LETTURA AUTOMATICA DEL "CERVELLO" DI OBSIDIAN ---
def leggi_cervello_obsidian(percorso_vault):
    regole = []
    if not percorso_vault or not os.path.exists(percorso_vault):
        return regole
    
    cartella_cervello = os.path.join(percorso_vault, "000_Cervello_AI")
    if os.path.exists(cartella_cervello):
        for file_md in os.listdir(cartella_cervello):
            if file_md.endswith(".md"):
                percorso_file = os.path.join(cartella_cervello, file_md)
                try:
                    with open(percorso_file, "r", encoding="utf-8") as f:
                        contenuto = f.read()
                        # Estrazione primitiva del Frontmatter YAML per recuperare le vecchie regole memorizzate
                        if contenuto.startswith("---"):
                            parti = contenuto.split("---")
                            lines = parti[1].strip().split("\n")
                            dati_regola = {}
                            for line in lines:
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    dati_regola[k.strip()] = v.strip().replace('"', '')
                            if "fornitore" in dati_regola:
                                regole.append(dati_regola)
                except:
                    pass
    return regole

# Funzione ausiliaria per generare l'XML standard FatturaPA
def genera_xml_autofattura(dati, imponibile_euro, is_forfettario):
    natura_iva = "N6.1" if dati.get("codice_autofattura_sdi") == "TD17" else "N6.2"
    aliquota = "22.00"
    imposta = round(imponibile_euro * 0.22, 2)
    
    if is_forfettario:
        natura_iva = "N2.2"
        aliquota = "0.00"
        imposta = 0.00

    root = ET.Element("p:FatturaElettronica", {
        "versione": "FPR12",
        "xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
        "xmlns:p": "http://www.fatturapa.gov.it/sdi/fatturapa/v1.2.2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
    })
    
    header = ET.SubElement(root, "FatturaElettronicaHeader")
    dati_trasmissione = ET.SubElement(header, "DatiTrasmissione")
    id_trasmittente = ET.SubElement(dati_trasmissione, "IdTrasmittente")
    ET.SubElement(id_trasmittente, "IdPaese").text = "IT"
    ET.SubElement(id_trasmittente, "IdCodice").text = "00000000000"
    ET.SubElement(dati_trasmissione, "ProgressivoInvio").text = "00001"
    ET.SubElement(dati_trasmissione, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(dati_trasmissione, "CodiceDestinatario").text = "0000000"
    
    cedente = ET.SubElement(header, "CedentePrestatore")
    dati_anagrafici_c = ET.SubElement(cedente, "DatiAnagrafici")
    id_fiscale_c = ET.SubElement(dati_anagrafici_c, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_c, "IdPaese").text = dati.get("paese_provenienza", "US")[:2].upper()
    ET.SubElement(id_fiscale_c, "IdCodice").text = str(dati.get("identificativo_fiscale_fornitore", "000000"))
    anagrafica_c = ET.SubElement(dati_anagrafici_c, "Anagrafica")
    ET.SubElement(anagrafica_c, "Denominazione").text = dati.get("fornitore", "Fornitore Estero")
    
    cessionario = ET.SubElement(header, "CessionarioCommittente")
    dati_anagrafici_cess = ET.SubElement(cessionario, "DatiAnagrafici")
    id_fiscale_cess = ET.SubElement(dati_anagrafici_cess, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_cess, "IdPaese").text = "IT"
    ET.SubElement(id_fiscale_cess, "IdCodice").text = "REMPLACE_WITH_USER_PIVA"
    anagrafica_cess = ET.SubElement(dati_anagrafici_cess, "Anagrafica")
    ET.SubElement(anagrafica_cess, "Denominazione").text = "TUA AZIENDA/CLIENTE SRL"

    corpo = ET.SubElement(root, "FatturaElettronicaBody")
    dati_generali = ET.SubElement(corpo, "DatiGenerali")
    dati_generali_doc = ET.SubElement(dati_generali, "DatiGeneraliDocumento")
    ET.SubElement(dati_generali_doc, "TipoDocumento").text = dati.get("codice_autofattura_sdi", "TD17")
    ET.SubElement(dati_generali_doc, "Divisa").text = "EUR"
    ET.SubElement(dati_generali_doc, "Data").text = dati.get("data_documento", "2026-01-01")
    ET.SubElement(dati_generali_doc, "Numero").text = "AFT-" + dati.get("data_documento", "20260101").replace("-", "")
    
    dati_beni_servizi = ET.SubElement(corpo, "DatiBeniServizi")
    dettaglio_linee = ET.SubElement(dati_beni_servizi, "DettaglioLinee")
    ET.SubElement(dettaglio_linee, "NumeroLinea").text = "1"
    ET.SubElement(dettaglio_linee, "Descrizione").text = f"Autofattura per {dati.get('categoria_costo_suggerita')} da {dati.get('fornitore')}"
    ET.SubElement(dettaglio_linee, "PrezzoUnitario").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dettaglio_linee, "PrezzoTotale").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dettaglio_linee, "AliquotaIVA").text = aliquota
    if is_forfettario or "N" in natura_iva:
        ET.SubElement(dettaglio_linee, "Natura").text = natura_iva

    dati_riepilogo = ET.SubElement(dati_beni_servizi, "DatiRiepilogo")
    ET.SubElement(dati_riepilogo, "AliquotaIVA").text = aliquota
    if is_forfettario or "N" in natura_iva:
        ET.SubElement(dati_riepilogo, "Natura").text = natura_iva
    ET.SubElement(dati_riepilogo, "ImponibileImporto").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dati_riepilogo, "Imposta").text = f"{imposta:.2f}"
    
    xml_string = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_string)
    return parsed_xml.toprettyxml(indent="  ")

# Funzione Anti-Blocco (Retry)
def chiama_gemini_con_retry(client, part, prompt, temp, max_tentativi=3):
    for tentativo in range(max_tentativi):
        try:
            risposta = client.models.generate_content(
                model='gemini-2.5-flash', contents=[part, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=DatiFatturaEstera, temperature=temp),
            )
            return risposta
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if tentativo < max_tentativi - 1:
                    time.sleep(5)
                    continue
                else:
                    raise Exception("I server di Google sono troppo carichi in questo momento. Riprova tra qualche minuto.")
            else:
                raise e

st.set_page_config(page_title="Piattaforma TaxTech AI", page_icon="🚀", layout="wide")

st.title("🚀 Ecosistema TaxTech: Obsidian Co-Pilot & Auto-Apprendimento")
st.write("L'interfaccia Streamlit ora legge e scrive direttamente dentro la cartella di Obsidian, usandolo come memoria centrale.")
st.write("---")

st.sidebar.title("⚙️ Connessione Real-Time Mac")
is_forfettario = st.sidebar.checkbox("🏢 Gestione Regime Forfettario", value=False)
conto_fornitore_estero = st.sidebar.text_input("Mastro Fornitori (AVERE)", "450101")
nome_cliente = st.sidebar.text_input("Nome Cliente Corrente (per Obsidian)", "Rossi_SRL")
percorso_obsidian = st.sidebar.text_input("Percorso Hub_Fiscale Mac", "/Users/liviobarcariolo/Desktop/Convertitore_Fatture_SaaS/Hub_Fiscale")

# Analisi in tempo reale di quello che Obsidian ha memorizzato nel suo "Vault"
regole_cervello = leggi_cervello_obsidian(percorso_obsidian)
if regole_cervello:
    st.sidebar.success(f"🧠 Connesso a Obsidian! Recuperate **{len(regole_cervello)} regole neurali** dal tuo Vault.")
else:
    st.sidebar.warning("⚠️ Nessuna regola trovata in `000_Cervello_AI`. Verrà creata automaticamente al primo salvataggio.")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    st.error("Inserisci la chiave GEMINI_API_KEY nei Secrets di Streamlit.")
else:
    client = genai.Client(api_key=api_key)
    
    files_caricati = st.file_uploader("Carica documenti (PDF o Immagini)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)
    
    if files_caricati:
        if st.button("🚀 Sincronizza ed Elabora con Cervello Obsidian"):
            lista_registro = []
            file_zip_buffer = io.BytesIO()
            
            import zipfile
            with zipfile.ZipFile(file_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # --- INIEZIONE DELLE REGOLE DI OBSIDIAN NEL PROMPT AI ---
                contesto_cervello = ""
                if regole_cervello:
                    contesto_cervello = "\n\nIMPORTANTE: Basati rigorosamente su queste regole storiche estratte direttamente dalla memoria del mio Obsidian Vault:\n"
                    for r in regole_cervello:
                        contesto_cervello += f"- Fornitore: '{r.get('fornitore')}' -> Categoria: '{r.get('categoria_costo_suggerita')}', Codice SDI: '{r.get('codice_autofattura_sdi')}'\n"

                prompt_base = "Esegui analisi contabile per il mercato italiano e rispondi rigorosamente seguendo lo schema JSON."
                prompt_finale = prompt_base + contesto_cervello
                
                for index, file in enumerate(files_caricati):
                    status_text.write(f"🔄 Interrogazione AI e allineamento cervello per: **{file.name}**...")
                    
                    try:
                        file_bytes = file.read()
                        mime_type = file.type
                        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                        
                        res1 = chiama_gemini_con_retry(client, part, prompt_finale, temp=0.1)
                        dati1 = json.loads(res1.text)
                        
                        res2 = chiama_gemini_con_retry(client, part, prompt_finale, temp=0.3)
                        dati2 = json.loads(res2.text)
                        
                        is_verified = (dati1["imponibile_valuta_originale"] == dati2["imponibile_valuta_originale"] and 
                                       dati1["codice_autofattura_sdi"] == dati2["codice_autofattura_sdi"])
                        stato_validazione = "✅ Verificato (100%)" if is_verified else "⚠️ Errore / Discrepanza Riscontrata"
                        
                        risultato = dati1.copy()
                        data_doc = risultato["data_documento"]
                        valuta_orig = risultato["valuta_originale"].upper()
                        importo_orig = risultato["imponibile_valuta_originale"]
                        
                        tasso_cambio_bce = 1.0
                        if valuta_orig != "EUR":
                            try:
                                url_api = f"https://api.frankfurter.app/{data_doc}?from={valuta_orig}&to=EUR"
                                risposta_bce = requests.get(url_api, timeout=5).json()
                                if "rates" in risposta_bce and "EUR" in risposta_bce["rates"]:
                                    tasso_cambio_bce = risposta_bce["rates"]["EUR"]
                            except Exception:
                                tasso_cambio_bce = 1.0
                        
                        imponibile_in_euro = round(importo_orig * tasso_cambio_bce, 2)
                        
                        # XML
                        xml_contenuto = genera_xml_autofattura(risultato, imponibile_in_euro, is_forfettario)
                        nome_file_xml = f"Fatture_XML/IT00000000000_{risultato['codice_autofattura_sdi']}_{index:05d}.xml"
                        zip_file.writestr(nome_file_xml, xml_contenuto)
                        
                        # --- NOTA DI SESSIONE PER OBSIDIAN ---
                        nome_fornitore_pulito = risultato['fornitore'].replace(' ', '_').replace('/', '_')
                        nome_nota_sessione = f"Sessione_{data_doc}_{nome_fornitore_pulito}.md"
                        contenuto_markdown = f"""---
tipo: registrazione_fiscale
fornitore: "{risultato['fornitore']}"
paese: "{risultato['paese_provenienza']}"
importo_euro: {imponibile_in_euro}
codice_sdi: "{risultato['codice_autofattura_sdi']}"
data_doc: {data_doc}
---
# Registrazione Operazione: {risultato['fornitore']}
Il cliente [[{nome_cliente}]] ha ricevuto un documento da [[{risultato['fornitore']}]] per la categoria **{risultato['categoria_costo_suggerita']}**.

Regola neurale collegata: [[Regola_{nome_fornitore_pulito}]]
"""
                        zip_file.writestr(f"300_Sessioni/{nome_nota_sessione}", contenuto_markdown)
                        
                        # --- AGGIORNAMENTO DINAMICO DELLA MEMORIA DI OBSIDIAN (`000_Cervello_AI`) ---
                        contenuto_regola_cervello = f"""---
tipo: regola_apprendimento_ai
fornitore: "{risultato['fornitore']}"
paese_provenienza: "{risultato['paese_provenienza']}"
categoria_costo_suggerita: "{risultato['categoria_costo_suggerita']}"
codice_autofattura_sdi: "{risultato['codice_autofattura_sdi']}"
---
# Regola di Apprendimento Automatica: {risultato['fornitore']}
Questa nota funge da memoria per il modello AI. Ogni modifica manuale effettuata qui dentro cambierà il comportamento dell'algoritmo alla prossima conversione.
"""
                        zip_file.writestr(f"000_Cervello_AI/Regola_{nome_fornitore_pulito}.md", contenuto_regola_cervello)
                        
                        # Scrittura fisica diretta se l'app è eseguita localmente sul Mac
                        if percorso_obsidian and os.path.exists(percorso_obsidian):
                            # Salva la sessione
                            c_sessioni = os.path.join(percorso_obsidian, "300_Sessioni")
                            os.makedirs(c_sessioni, exist_ok=True)
                            with open(os.path.join(c_sessioni, nome_nota_sessione), "w", encoding="utf-8") as f:
                                f.write(contenuto_markdown)
                                
                            # Salva/Aggiorna la regola nel cervello
                            c_cervello = os.path.join(percorso_obsidian, "000_Cervello_AI")
                            os.makedirs(c_cervello, exist_ok=True)
                            with open(os.path.join(c_cervello, f"Regola_{nome_fornitore_pulito}.md"), "w", encoding="utf-8") as f:
                                f.write(contenuto_regola_cervello)
                        
                        risultato["File"] = file.name
                        risultato["Imponibile (€)"] = imponibile_in_euro
                        risultato["Controllo AI"] = stato_validazione
                        lista_registro.append(risultato)
                        
                    except Exception as e:
                        st.error(f"Errore sul file {file.name}: {e}")
                    
                    progress_bar.progress((index + 1) / len(files_caricati))
                
                status_text.empty()
                
                if lista_registro:
                    st.success("🎯 Sincronizzazione completata con il cervello di Obsidian!")
                    df_reg = pd.DataFrame(lista_registro)
                    st.dataframe(df_reg[["File", "fornitore", "data_documento", "Imponibile (€)", "codice_autofattura_sdi", "Controllo AI"]], use_container_width=True)
                    
                    zip_file.close()
                    file_zip_buffer.seek(0)
                    
                    st.download_button(
                        label="🚀 SCARICA AGGIORNAMENTO COMPLETO PER IL VAULT OBSIDIAN & SDI",
                        data=file_zip_buffer,
                        file_name="aggiornamento_hub_fiscale.zip",
                        mime="application/zip"
                    )
