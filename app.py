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
import time
import zipfile

# --- CONFIGURAZIONE WEBHOOK PER IL TUO CERVELLO OBSIDIAN ---
URL_WEBHOOK_CERVELLO = "https://hook.eu2.make.com/tuo-codice-webhook-personale"

# Mappatura Automatica Piano dei Conti (Dare / Avere)
MAP_DARE_AVERE = {
    "Software SaaS": {"dare": "3006001", "avere": "4010002", "desc": "Costi per Software SaaS"},
    "Hosting/Cloud": {"dare": "3006002", "avere": "4010002", "desc": "Spese Hosting e Cloud Server"},
    "Pubblicità/Marketing": {"dare": "3012005", "avere": "4010002", "desc": "Spese di Pubblicità e Marketing"},
    "Beni strumentali": {"dare": "1004001", "avere": "4010002", "desc": "Acquisto Hardware / Attrezzature"},
    "Consulenza": {"dare": "3009001", "avere": "4010002", "desc": "Spese per Consulenze Tecniche"}
}

def invia_al_cervello_centralizzato(dati, nome_cliente, imponibile_euro, conto_dare, conto_avere):
    payload = {
        "cliente_studio": nome_cliente,
        "fornitore": dati.get("fornitore"),
        "identificativo_fiscale_fornitore": dati.get("identificativo_fiscale_fornitore"),
        "paese_provenienza": dati.get("paese_provenienza"),
        "categoria_costo_suggerita": dati.get("categoria_costo_suggerita"),
        "conto_dare": conto_dare,
        "conto_avere": conto_avere,
        "codice_autofattura_sdi": dati.get("codice_autofattura_sdi"),
        "imponibile_euro": imponibile_euro,
        "data_documento": dati.get("data_documento")
    }
    try:
        requests.post(URL_WEBHOOK_CERVELLO, json=payload, timeout=5)
    except Exception:
        pass

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

# Funzione corretta per generare l'XML standard senza errori di ElementTree
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
    
    # RISOLTO: Corretto il posizionamento del CodiceDestinatario
    codice_destinatario = ET.SubElement(dati_trasmissione, "CodiceDestinatario")
    codice_destinatario.text = "0000000"
    
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

def chiama_gemini_con_retry(client, part, prompt, temp, max_tentativi=3):
    for tentativo in range(max_tentativi):
        try:
            risposta = client.models.generate_content(
                model='gemini-2.5-flash', contents=[part, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=DatiFatturaEstera, temperature=temp),
            )
            return risposta
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                raise Exception("⚠️ HAI ESAURITO LA QUOTA GIORNALIERA GRATUITA DI GEMINI (20 file/giorno). Per sbloccarla, inserisci una carta di credito su Google AI Studio (piano Pay-as-you-go, costa meno di 0,001€ a fattura).")
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if tentativo < max_tentativi - 1:
                    time.sleep(5)
                    continue
                else:
                    raise Exception("I server di Google sono momentaneamente sovraccarichi. Riprova.")
            else:
                raise e

st.set_page_config(page_title="Piattaforma TaxTech AI", page_icon="🚀", layout="wide")

st.title("🚀 Ecosistema TaxTech: Conversione Cloud")
st.write("Carica i documenti esteri per la generazione automatica dei file XML conformi per lo SDI.")
st.write("---")

st.sidebar.title("⚙️ Dati Cliente")
is_forfettario = st.sidebar.checkbox("🏢 Gestione Regime Forfettario", value=False)
nome_cliente = st.sidebar.text_input("Ragione Sociale Cliente", "Cliente_SRL")

# --- ⚖️ SEZIONE TUTELA LEGALE E PRIVACY COMPLIANCE ---
st.write("### ⚖️ Note Legali, Limitazione di Responsabilità e Privacy")
with st.expander("Clicca qui per leggere l'Informativa GDPR (Ex Art. 13) e i Termini di Esonero Responsabilità (Ex Artt. 1229 e 2236 C.C.)"):
    st.markdown("""
    **1. INFORMATIVA PRIVACY (Ex Art. 13 Regolamento UE 2016/679 - GDPR)**... *(testo privacy invariato)*
    """)

accettazione_legale = st.checkbox("Dichiaro di aver letto e compreso l'informativa, accetto incondizionatamente i termini di manleva (Artt. 1229 e 2236 C.C.) e presto il consenso al trattamento dei dati personali (Art. 13 GDPR).")

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
        if st.button("🚀 Converti in XML e Invia a Studio", disabled=not accettazione_legale):
            lista_registro = []
            file_zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(file_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                progress_bar = st.progress(0)
                status_text = st.empty()
                prompt_finale = "Esegui analisi contabile per il mercato italiano e rispondi rigorosamente seguendo lo schema JSON."
                
                for index, file in enumerate(files_caricati):
                    status_text.write(f"🔄 Elaborazione AI per: **{file.name}**...")
                    
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
                        stato_validazione = "✅ Verificato" if is_verified else "⚠️ Discrepanza"
                        
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
                        
                        # --- ABBINAMENTO AUTOMATICO DARE / AVERE ---
                        categoria = risultato.get("categoria_costo_suggerita", "Software SaaS")
                        conti = MAP_DARE_AVERE.get(categoria, {"dare": "3006001", "avere": "4010002"})
                        
                        # Generazione XML SDI sicuro
                        xml_contenuto = genera_xml_autofattura(risultato, imponibile_in_euro, is_forfettario)
                        nome_file_xml = f"Fatture_XML/IT00000000000_{risultato['codice_autofattura_sdi']}_{index:05d}.xml"
                        zip_file.writestr(nome_file_xml, xml_contenuto)
                        
                        # Invio ad Obsidian con Dare/Avere inclusi!
                        invia_al_cervello_centralizzato(risultato, nome_cliente, imponibile_in_euro, conti["dare"], conti["avere"])
                        
                        # Popolamento Tabella Streamlit
                        risultato["File"] = file.name
                        risultato["Imponibile (€)"] = imponibile_in_euro
                        risultato["Conto Dare"] = conti["dare"]
                        risultato["Conto Avere"] = conti["avere"]
                        risultato["Controllo AI"] = stato_validazione
                        lista_registro.append(risultato)
                        
                    except Exception as e:
                        st.error(f"Errore sul file {file.name}: {e}")
                    
                    progress_bar.progress((index + 1) / len(files_caricati))
                
                status_text.empty()
                
                if lista_registro:
                    st.success("🎯 Elaborazione completata!")
                    df_reg = pd.DataFrame(lista_registro)
                    # Mostra a schermo anche i conti Dare e Avere
                    st.dataframe(df_reg[["File", "fornitore", "Imponibile (€)", "Conto Dare", "Conto Avere", "codice_autofattura_sdi", "Controllo AI"]], use_container_width=True)
                    
                    zip_file.close()
                    file_zip_buffer.seek(0)
                    st.download_button(label="🚀 SCARICA PACCHETTO XML PER LO SDI", data=file_zip_buffer, file_name="autofatture_sdi.zip", mime="application/zip")
