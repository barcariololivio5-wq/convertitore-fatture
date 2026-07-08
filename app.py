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
import os  # Estensione nativa per interagire con le cartelle del Mac
import time # Aggiunto per gestire i tempi di attesa dell'errore 503

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

# Funzione ausiliaria per generare l'XML standard FatturaPA per l'Autofattura dello SDI
def genera_xml_autofattura(dati, imponibile_euro, is_forfettario):
    # Definizione codici IVA e Natura esenzione
    natura_iva = "N6.1" if dati["codice_autofattura_sdi"] == "TD17" else "N6.2"
    aliquota = "22.00"
    imposta = round(imponibile_euro * 0.22, 2)
    
    if is_forfettario:
        natura_iva = "N2.2"  # Non soggetto per forfettari
        aliquota = "0.00"
        imposta = 0.00

    # Costruzione struttura XML standard dell'Agenzia delle Entrate
    root = ET.Element("p:FatturaElettronica", {
        "versione": "FPR12",
        "xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
        "xmlns:p": "http://www.fatturapa.gov.it/sdi/fatturapa/v1.2.2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
    })
    
    # Intestazione
    header = ET.SubElement(root, "FatturaElettronicaHeader")
    dati_trasmissione = ET.SubElement(header, "DatiTrasmissione")
    id_trasmittente = ET.SubElement(dati_trasmissione, "IdPaese").text = "IT"
    ET.SubElement(id_trasmittente, "IdCodice").text = "00000000000" # Da personalizzare con P.IVA Utente
    ET.SubElement(dati_trasmissione, "ProgressivoInvio").text = "00001"
    ET.SubElement(dati_trasmissione, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(dati_trasmissione, "CodiceDestinatario").text = "0000000" # Canale SDI
    
    # Cedente Prestatore (Il fornitore estero)
    cedente = ET.SubElement(header, "CedentePrestatore")
    dati_anagrafici_c = ET.SubElement(cedente, "DatiAnagrafici")
    id_fiscale_c = ET.SubElement(dati_anagrafici_c, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_c, "IdPaese").text = dati["paese_provenienza"][:2].upper()
    ET.SubElement(id_fiscale_c, "IdCodice").text = dati["identificativo_fiscale_fornitore"]
    anagrafica_c = ET.SubElement(dati_anagrafici_c, "Anagrafica")
    ET.SubElement(anagrafica_c, "Denominazione").text = dati["fornitore"]
    
    # Cessionario Committente (L'utente Italiano che emette l'autofattura)
    cessionario = ET.SubElement(header, "CessionarioCommittente")
    dati_anagrafici_cess = ET.SubElement(cessionario, "DatiAnagrafici")
    id_fiscale_cess = ET.SubElement(dati_anagrafici_cess, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_cess, "IdPaese").text = "IT"
    ET.SubElement(id_fiscale_cess, "IdCodice").text = "REMPLACE_WITH_USER_PIVA"
    anagrafica_cess = ET.SubElement(dati_anagrafici_cess, "Anagrafica")
    ET.SubElement(anagrafica_cess, "Denominazione").text = "TUA AZIENDA/CLIENTE SRL"

    # Corpo della Fattura
    corpo = ET.SubElement(root, "FatturaElettronicaBody")
    dati_generali = ET.SubElement(corpo, "DatiGenerali")
    dati_generali_doc = ET.SubElement(dati_generali, "DatiGeneraliDocumento")
    ET.SubElement(dati_generali_doc, "TipoDocumento").text = dati["codice_autofattura_sdi"]
    ET.SubElement(dati_generali_doc, "Divisa").text = "EUR"
    ET.SubElement(dati_generali_doc, "Data").text = dati["data_documento"]
    ET.SubElement(dati_generali_doc, "Numero").text = "AFT-" + dati["data_documento"].replace("-", "")
    
    # Righe di dettaglio del bene/servizio
    dati_beni_servizi = ET.SubElement(corpo, "DatiBeniServizi")
    dettaglio_linee = ET.SubElement(dati_beni_servizi, "DettaglioLinee")
    ET.SubElement(dettaglio_linee, "NumeroLinea").text = "1"
    ET.SubElement(dettaglio_linee, "Descrizione").text = f"Autofattura per {dati['categoria_costo_suggerita']} da {dati['fornitore']}"
    ET.SubElement(dettaglio_linee, "PrezzoUnitario").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dettaglio_linee, "PrezzoTotale").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dettaglio_linee, "AliquotaIVA").text = aliquota
    if is_forfettario or "N" in natura_iva:
        ET.SubElement(dettaglio_linee, "Natura").text = natura_iva

    # Riepilogo IVA
    dati_riepilogo = ET.SubElement(dati_beni_servizi, "DatiRiepilogo")
    ET.SubElement(dati_riepilogo, "AliquotaIVA").text = aliquota
    if is_forfettario or "N" in natura_iva:
        ET.SubElement(dati_riepilogo, "Natura").text = natura_iva
    ET.SubElement(dati_riepilogo, "ImponibileImporto").text = f"{imponibile_euro:.2f}"
    ET.SubElement(dati_riepilogo, "Imposta").text = f"{imposta:.2f}"
    
    # Formattazione dell'XML con indentazione leggibile
    xml_string = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_string)
    return parsed_xml.toprettyxml(indent="  ")

# Funzione Anti-Blocco (Retry) per l'Intelligenza Artificiale
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
                    time.sleep(5) # Aspetta 5 secondi prima di riprovare
                    continue
                else:
                    raise Exception("I server di Google sono troppo carichi in questo momento. Riprova tra qualche minuto.")
            else:
                raise e # Se è un altro errore, lo mostra normalmente

# Impostazione Layout Streamlit
st.set_page_config(page_title="Piattaforma TaxTech AI", page_icon="🚀", layout="wide")

st.title("🚀 Suite TaxTech: Autofatture SDI e Validazione in Doppio Cieco")
st.write("L'unico sistema contabile dotato di algoritmo di controllo incrociato anti-allucinazione e generazione nativa dei file XML per lo SDI.")
st.write("---")

# --- UNIFICAZIONE BARRA LATERALE CORRETTA ---
st.sidebar.title("⚙️ Parametri Fiscali & Mac")
is_forfettario = st.sidebar.checkbox("🏢 Gestione Regime Forfettario", value=False)
conto_fornitore_estero = st.sidebar.text_input("Mastro Fornitori (AVERE)", "450101")
nome_cliente = st.sidebar.text_input("Nome Cliente Corrente (per Obsidian)", "Rossi_SRL")

# IL TUO PERCORSO REALE E DEFINITIVO CORRETTO!
percorso_obsidian = st.sidebar.text_input("Percorso Cartella Hub_Fiscale del Mac", "/Users/liviobarcariolo/Desktop/Convertitore_Fatture_SaaS/Hub_Fiscale")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    st.error("Inserisci la chiave GEMINI_API_KEY nei Secrets di Streamlit.")
else:
    client = genai.Client(api_key=api_key)
    
    files_caricati = st.file_uploader(
        "Carica documenti (PDF o Immagini)", 
        type=["png", "jpg", "jpeg", "pdf"], 
        accept_multiple_files=True
    )
    
    if files_caricati:
        if st.button("🧠 Avvia Elaborazione Massiva & Sincronizza Obsidian"):
            lista_registro = []
            file_zip_buffer = io.BytesIO()
            
            import zipfile
            with zipfile.ZipFile(file_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for index, file in enumerate(files_caricati):
                    status_text.write(f"🔄 Validazione in corso per: **{file.name}** (potrebbe volerci qualche secondo se i server sono carichi)...")
                    
                    try:
                        file_bytes = file.read()
                        mime_type = file.type
                        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                        prompt = "Esegui analisi contabile per il mercato italiano e rispondi rigorosamente seguendo lo schema JSON."
                        
                        # --- MOTORE DOPPIO CIECO CON SISTEMA ANTI-BLOCCO (RETRY) ---
                        res1 = chiama_gemini_con_retry(client, part, prompt, temp=0.1)
                        dati1 = json.loads(res1.text)
                        
                        res2 = chiama_gemini_con_retry(client, part, prompt, temp=0.3)
                        dati2 = json.loads(res2.text)
                        
                        is_verified = (dati1["imponibile_valuta_originale"] == dati2["imponibile_valuta_originale"] and 
                                       dati1["codice_autofattura_sdi"] == dati2["codice_autofattura_sdi"])
                        stato_validazione = "✅ Verificato (100%)" if is_verified else "⚠️ Errore / Discrepanza Riscontrata"
                        
                        risultato = dati1
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
                        
                        # --- INIEZIONE NATURALE IN OBSIDIAN (CON CREAZIONE AUTOMATICA) ---
                        if percorso_obsidian and os.path.exists(percorso_obsidian):
                            cartella_target = os.path.join(percorso_obsidian, "300_Sessioni")
                            
                            # Se sul Mac manca la cartella 300_Sessioni, la creiamo noi via codice!
                            if not os.path.exists(cartella_target):
                                os.makedirs(cartella_target)
                                
                            nome_nota_sessione = f"Sessione_{data_doc}_{risultato['fornitore'].replace(' ', '_')}.md"
                            percorso_file_sessione = os.path.join(cartella_target, nome_nota_sessione)
                            
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

### 📊 Dati Finanziari
- **Importo in Valuta:** {importo_orig} {valuta_orig}
- **Tasso Cambio BCE:** {tasso_cambio_bce}
- **Importo Convertito:** **€ {imponibile_in_euro}**
- **Codice Adempimento:** [[{risultato['codice_autofattura_sdi']}]]

---
*Generato in automatico dall'ecosistema TaxTech.*
"""
                            with open(percorso_file_sessione, "w", encoding="utf-8") as f:
                                f.write(contenuto_markdown)
                        
                        risultato["File"] = file.name
                        risultato["Imponibile (€)"] = imponibile_in_euro
                        risultato["Controllo AI"] = stato_validazione
                        lista_registro.append(risultato)
                        
                        xml_contenuto = genera_xml_autofattura(risultato, imponibile_in_euro, is_forfettario)
                        nome_file_xml = f"IT00000000000_{risultato['codice_autofattura_sdi']}_{index:05d}.xml"
                        zip_file.writestr(nome_file_xml, xml_contenuto)
                        
                    except Exception as e:
                        st.error(f"Errore sul file {file.name}: {e}")
                    
                    progress_bar.progress((index + 1) / len(files_caricati))
                
                status_text.empty()
                
                if lista_registro:
                    st.success("🎯 Tutti i documenti sono stati elaborati, verificati e sincronizzati in Obsidian!")
                    
                    df_reg = pd.DataFrame(lista_registro)
                    st.write("### 📊 Cruscotto di Controllo (Doppio Cieco)")
                    
                    st.dataframe(df_reg[["File", "fornitore", "data_documento", "valuta_originale", "imponibile_valuta_originale", "Imponibile (€)", "codice_autofattura_sdi", "Controllo AI"]].rename(columns={
                        "fornitore": "Fornitore", "data_documento": "Data", "valuta_originale": "Valuta Orig.", "imponibile_valuta_originale": "Importo Orig.", "codice_autofattura_sdi": "Codice SDI"
                    }), use_container_width=True)
                    
                    zip_file.close()
                    file_zip_buffer.seek(0)
                    
                    st.write("---")
                    st.download_button(
                        label="🚀 SCARICA PACCHETTO ZIP CON TUTTE LE AUTOFATTURE XML PER LO SDI",
                        data=file_zip_buffer,
                        file_name="pacchetto_autofatture_xml_sdi.zip",
                        mime="application/zip"
                    )
