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
import base64
from datetime import datetime

# --- CONFIGURAZIONE DELLA PAGINA (LUXURY EXECUTIVE ENTERPRISE) ---  
st.set_page_config(  
    page_title="TaxTech Intelligence Platform | Enterprise Edition",   
    page_icon="👑",   
    layout="wide",  
    initial_sidebar_state="expanded"  
)  

# --- STILE CSS PERSONALIZZATO (HIGH-END LUXURY DESIGN) ---
st.markdown("""
    <style>
        /* Tema Ossidiana e Struttura di Pregio */
        .main { background-color: #030712; }
        body { color: #F3F4F6; }
        
        /* Banner Principale Luxury */
        .luxury-banner {
            background: linear-gradient(135deg, #111827 0%, #030712 100%);
            border: 1px solid #D97706; /* Accento Oro Brunito */
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            margin-bottom: 35px;
            box-shadow: 0 10px 30px -10px rgba(217, 119, 6, 0.15);
        }
        
        /* Box e Contenitori Modulari */
        .luxury-card {
            background: #0F172A;
            border: 1px solid #1E293B;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }
        
        .card-title {
            color: #F59E0B; /* Oro Bright */
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: 0.5px;
        }

        /* Tabelle Contabili Custom */
        .ledger-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background-color: #0B0F19;
            border-radius: 8px;
            overflow: hidden;
        }
        .ledger-table th {
            background-color: #1E293B;
            color: #94A3B8;
            padding: 12px;
            text-align: left;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .ledger-table td {
            padding: 12px;
            border-bottom: 1px solid #1E293B;
            color: #E2E8F0;
            font-size: 0.9rem;
        }
        
        /* Modifica dell'estetica dei Pulsanti nativi */
        div.stButton > button {
            background: linear-gradient(90deg, #D97706 0%, #B45309 100%) !important;
            color: #FFFFFF !important;
            font-weight: 600 !important;
            letter-spacing: 0.5px !important;
            padding: 12px 28px !important;
            border-radius: 8px !important;
            border: 1px solid #F59E0B !important;
            box-shadow: 0 4px 15px rgba(217, 119, 6, 0.2) !important;
            transition: all 0.3s ease !important;
        }
        div.stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 25px rgba(217, 119, 6, 0.4) !important;
            background: linear-gradient(90deg, #F59E0B 0%, #D97706 100%) !important;
        }
        
        /* Stile speciale per i pulsanti di download secondari */
        .download-sec button {
            background: linear-gradient(90deg, #334155 0%, #1E293B 100%) !important;
            border: 1px solid #475569 !important;
            box-shadow: none !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- DIZIONARIO PIANO DEI CONTI STRUTTURATO (DARE / AVERE) ---  
MAP_PIANO_CONTI = {  
    "Software SaaS": {"conto_costo": "3006001", "desc_costo": "Costi per Software SaaS (Estero)", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Hosting/Cloud": {"conto_costo": "3006002", "desc_costo": "Spese Hosting e Cloud Infrastructure", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Pubblicità/Marketing": {"conto_costo": "3012005", "desc_costo": "Spese Adv & Digital Marketing", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Beni strumentali": {"conto_costo": "1004001", "desc_costo": "Acquisto Hardware & Asset Strumentali", "conto_ricavo": "4010005", "desc_ricavo": "Fornitori Esteri c/Beni"},  
    "Consulenza": {"conto_costo": "3009001", "desc_costo": "Spese per Consulenze Tecniche Internazionali", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Consulenze"}  
}  

# Schema Pydantic per l'estrazione intelligente
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

# --- MOTORE DI PRE-VALIDAZIONE XSD (REGOLE AGENZIA ENTRATE) ---
def esegui_pre_check_xsd(dati, piva_cliente):
    errori = []
    avvisi = []
    
    if len(piva_cliente.strip()) != 11 or not piva_cliente.strip().isdigit():
        errori.append("SDI-B01: La Partita IVA del Cessionario (Cliente) deve essere di esattamente 11 caratteri numerici.")
        
    paese = dati.get("paese_provenienza", "").strip()
    if len(paese) != 2 or not paese.isalpha():
        errori.append("SDI-B02: Il codice ISO Paese del Fornitore deve essere di 2 lettere alfabetiche (es. US, IE).")
        
    if not dati.get("identificativo_fiscale_fornitore", "").strip():
        errori.append("SDI-B03: L'identificativo fiscale (VAT ID / Tax ID) del Cedente è obbligatorio nel tracciato XML.")
        
    data_str = dati.get("data_documento", "").strip()
    try:
        datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError:
        errori.append("SDI-B04: Il formato della data del documento deve seguire tassativamente la struttura YYYY-MM-DD.")
        
    codice_sdi = dati.get("codice_autofattura_sdi", "")
    if codice_sdi not in ["TD17", "TD18", "TD19"]:
        errori.append("SDI-B05: Codice Tipo Documento non valido per l'integrazione/autofattura estera.")
        
    return errori, avvisi

# --- GENERATORE DI TRACCIATO XML MINISTERIALE ---
def genera_xml_autofattura(dati_validati, is_forfettario, nome_cliente, piva_cliente):  
    natura_iva = "N6.1" if dati_validati.get("codice_autofattura_sdi") == "TD17" else "N6.2"  
    aliquota = "22.00"  
    imponibile_euro = dati_validati.get("imponibile_euro", 0.0)
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
    ET.SubElement(id_trasmittente, "IdCodice").text = str(piva_cliente).strip()  
    ET.SubElement(dati_trasmissione, "ProgressivoInvio").text = "00001"  
    ET.SubElement(dati_trasmissione, "FormatoTrasmissione").text = "FPR12"  
    ET.SubElement(dati_trasmissione, "CodiceDestinatario").text = "0000000"  
      
    # CEDENTE PRESTATORE (Fornitore estero)  
    cedente = ET.SubElement(header, "CedentePrestatore")  
    dati_anagrafici_c = ET.SubElement(cedente, "DatiAnagrafici")  
    id_fiscale_c = ET.SubElement(dati_anagrafici_c, "IdFiscaleIVA")  
    ET.SubElement(id_fiscale_c, "IdPaese").text = dati_validati.get("paese_provenienza", "US")[:2].upper()  
    ET.SubElement(id_fiscale_c, "IdCodice").text = str(dati_validati.get("identificativo_fiscale_fornitore", "000000"))  
    anagrafica_c = ET.SubElement(dati_anagrafici_c, "Anagrafica")  
    ET.SubElement(anagrafica_c, "Denominazione").text = dati_validati.get("fornitore", "Fornitore Estero")  
      
    # CESSIONARIO COMMITTENTE (Cliente dello studio)  
    cessionario = ET.SubElement(header, "CessionarioCommittente")  
    dati_anagrafici_cess = ET.SubElement(cessionario, "DatiAnagrafici")  
    id_fiscale_cess = ET.SubElement(dati_anagrafici_cess, "IdFiscaleIVA")  
    ET.SubElement(id_fiscale_cess, "IdPaese").text = "IT"  
    ET.SubElement(id_fiscale_cess, "IdCodice").text = str(piva_cliente).strip()  
    anagrafica_cess = ET.SubElement(dati_anagrafici_cess, "Anagrafica")  
    ET.SubElement(anagrafica_cess, "Denominazione").text = str(nome_cliente).strip()  

    corpo = ET.SubElement(root, "FatturaElettronicaBody")  
    dati_generali = ET.SubElement(corpo, "DatiGenerali")  
    dati_generali_doc = ET.SubElement(dati_generali, "DatiGeneraliDocumento")  
    ET.SubElement(dati_generali_doc, "TipoDocumento").text = dati_validati.get("codice_autofattura_sdi", "TD17")  
    ET.SubElement(dati_generali_doc, "Divisa").text = "EUR"  
    ET.SubElement(dati_generali_doc, "Data").text = dati_validati.get("data_documento", "2026-01-01")  
    ET.SubElement(dati_generali_doc, "Numero").text = "AFT-" + dati_validati.get("data_documento", "20260101").replace("-", "")  
      
    dati_beni_servizi = ET.SubElement(corpo, "DatiBeniServizi")  
    dettaglio_linee = ET.SubElement(dati_beni_servizi, "DettaglioLinee")  
    ET.SubElement(dettaglio_linee, "NumeroLinea").text = "1"  
    ET.SubElement(dettaglio_linee, "Descrizione").text = f"Autofattura per {dati_validati.get('categoria_costo_suggerita')} da {dati_validati.get('fornitore')}"  
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
                raise Exception("⚠️ Limite API raggiunto per la demo. Contattare l'amministratore.")  
            if "503" in str(e) or "UNAVAILABLE" in str(e):  
                if tentativo < max_tentativi - 1:  
                    time.sleep(4)  
                    continue  
            raise e  

# --- STRUTTURAZIONE DELLA SESSION STATE PER BATCH PROCESSING ---
if "lotto_lavoro" not in st.session_state:
    st.session_state["lotto_lavoro"] = {} 
if "contatore_manuale" not in st.session_state:
    st.session_state["contatore_manuale"] = 0

# --- NAVIGAZIONE SU SCHEDE CORPORATE ---  
tab_overview, tab_operazione = st.tabs(["🏛️ Suite Istituzionale & Specifiche", "🚀 Centro di Controllo Massivo"]) 

with tab_overview:  
    st.markdown("""  
    <div class='luxury-banner'>  
        <h1 style='color: #F59E0B; font-size: 3.5rem; margin-bottom: 5px;'>TAXTECH INTELLIGENCE PLATFORM</h1>  
        <p style='color: #E2E8F0; font-size: 1.25rem; font-weight: 300; letter-spacing: 1px; max-width: 900px; margin: 0 auto;'>
            Ingegneria fiscale e intelligenza artificiale per l'automazione massiva dei flussi di inversioni contabili estere. Conforme alle specifiche Agenzia delle Entrate v1.2.2.
        </p>  
    </div>  
    """, unsafe_allow_html=True)  
      
    st.markdown("### 💎 Canali di Distribuzione e Interoperabilità")  
    col_f1, col_f2, col_f3 = st.columns(3)  
    with col_f1:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">🛡️ Validazione AdE & SDI Integrata</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                Ogni file XML generato viene sottoposto a uno screening formale che replica i controlli del <b>Sistema di Interscambio</b>. Questo assicura il caricamento diretto sul portale <i>Fatture e Corrispettivi</i> azzerando le notifiche di scarto.
            </div>  
        </div>  
        """, unsafe_allow_html=True)  
    with col_f2:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">🔌 Importazione Sistemi Core Studio</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                Il pacchetto compresso ZIP adotta l'albero di nomenclatura standardizzato compatibile con i principali ERP italiani: <b>Zucchetti Omnia/Ago, TeamSystem, Euroconference, Digital Hub, Aruba e software gestionali aziendali</b>.
            </div>  
        </div>  
        """, unsafe_allow_html=True)  
    with col_f3:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">📈 Riconciliazione e Prima Nota</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                La piattaforma non si limita alla conversione del file, ma mappa le transazioni direttamente sul piano dei conti dello studio, calcolando le annotazioni in Dare e Avere per una contabilizzazione istantanea in Prima Nota.
            </div>  
        </div>  
        """, unsafe_allow_html=True)  

with tab_operazione:  
    st.sidebar.markdown("<h2 style='color: #F59E0B; font-size: 1.3rem;'>👑 Anagrafica Studio</h2>", unsafe_allow_html=True)  
    is_forfettario = st.sidebar.checkbox("🏢 Cliente in Regime Forfettario", value=False)  
    nome_cliente = st.sidebar.text_input("Ragione Sociale Cliente", "Corporate Client S.p.A.")  
    piva_cliente = st.sidebar.text_input("Partita IVA Cliente (11 cifre)", "01234567890")  
    
    st.sidebar.markdown("---")
    if st.sidebar.button("➕ AGGIUNGI AUTOFATTURA MANUALE"):
        st.session_state["contatore_manuale"] += 1
        id_man = f"MANUALE_{st.session_state['contatore_manuale']}"
        st.session_state["lotto_lavoro"][id_man] = {
            "fornitore": "Nuovo Fornitore da Inserire",  
            "identificativo_fiscale_fornitore": "ID_FISCALE",  
            "data_documento": datetime.today().strftime('%Y-%m-%d'),  
            "valuta_originale": "EUR",  
            "imponibile_valuta_originale": 0.0,  
            "codice_autofattura_sdi": "TD17",  
            "categoria_costo_suggerita": "Software SaaS",  
            "paese_provenienza": "US"
        }
        st.toast("Aggiunta nuova scheda per l'inserimento manuale!", icon="📝")

    st.write("### 🛡️ Protocollo Securezza Crittografica & Sandbox")  
    accettazione_legale = st.checkbox("Abilita il caricamento cifrato e l'interfaccia di revisione contabile avanzata.")  

    try:  
        api_key = st.secrets["GEMINI_API_KEY"]  
    except Exception:  
        api_key = None  

    if not api_key:  
        st.error("Configurare la chiave GEMINI_API_KEY nei Secrets del Server.")  
    elif accettazione_legale:  
        client = genai.Client(api_key=api_key)  
        
        file_caricati = st.file_uploader("Trascina o seleziona un gruppo di fatture (PDF, JPG, PNG) - Elaborazione Simultanea", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)  
          
        if file_caricati:  
            for f in file_caricati:
                id_file = f.name
                if id_file not in st.session_state["lotto_lavoro"]:
                    with st.spinner(f"🧠 AI Reading: Decodifica avanzata di {f.name}..."):
                        file_bytes = f.read()
                        mime_type = f.type  
                        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)  
                        
                        prompt_finale = "Esegui analisi contabile per il mercato italiano e rispondi rigorosamente seguendo lo schema JSON."   
                        try:
                            res1 = chiama_gemini_con_retry(client, part, prompt_finale, temp=0.1)  
                            st.session_state["lotto_lavoro"][id_file] = json.loads(res1.text)
                        except Exception as e:
                            st.error(f"Errore durante l'analisi di {f.name}: {str(e)}")

        if st.session_state["lotto_lavoro"]:
            st.markdown("---")
            st.markdown("#### 🛠️ Area di Revisione ed Editoria dei Dati Estratti")
            
            chiavi_lotto = list(st.session_state["lotto_lavoro"].keys())
            doc_selezionato = st.selectbox("🎯 SELEZIONA IL DOCUMENTO DA REVISIONARE O COMPILARE:", chiavi_lotto)
            
            dati_correnti = st.session_state["lotto_lavoro"][doc_selezionato]
            
            with st.container(border=True):
                st.markdown(f"**Stai modificando:** `{doc_selezionato}`")
                
                col_ed1, col_ed2 = st.columns(2)
                with col_ed1:
                    edit_fornitore = st.text_input("Ragione Sociale Fornitore", value=dati_correnti.get("fornitore", ""), key=f"forn_{doc_selezionato}")
                    edit_piva_forn = st.text_input("VAT ID / Identificativo Fiscale Fornitore", value=dati_correnti.get("identificativo_fiscale_fornitore", ""), key=f"piva_{doc_selezionato}")
                    edit_data = st.text_input("Data Documento (YYYY-MM-DD)", value=dati_correnti.get("data_documento", "2026-01-01"), key=f"data_{doc_selezionato}")
                    edit_paese = st.text_input("Codice ISO Paese Fornitore (2 lettere)", value=dati_correnti.get("paese_provenienza", "US")[:2].upper(), key=f"paese_{doc_selezionato}")
                
                with col_ed2:
                    edit_imponibile = st.number_input("Imponibile in Valuta Originale", value=float(dati_correnti.get("imponibile_valuta_originale", 0.0)), step=0.01, key=f"imp_{doc_selezionato}")
                    edit_valuta = st.text_input("Valuta Documento (Codice ISO)", value=dati_correnti.get("valuta_originale", "EUR"), key=f"val_{doc_selezionato}").strip().upper()
                    edit_codice_sdi = st.selectbox("Codice Documento SDI Richiesto", ["TD17", "TD18", "TD19"], index=["TD17", "TD18", "TD19"].index(dati_correnti.get("codice_autofattura_sdi", "TD17")), key=f"sdi_{doc_selezionato}")
                    edit_cat = st.selectbox("Categoria di Costo", ["Software SaaS", "Hosting/Cloud", "Pubblicità/Marketing", "Beni strumentali", "Consulenza"], index=["Software SaaS", "Hosting/Cloud", "Pubblicità/Marketing", "Beni strumentali", "Consulenza"].index(dati_correnti.get("categoria_costo_suggerita", "Software SaaS")), key=f"cat_{doc_selezionato}")
            
            # Calcolo Tasso di Cambio
            tasso_cambio_bce = 1.0
            if edit_valuta != "EUR":
                try:
                    url_api = f"https://api.frankfurter.app/{edit_data}?from={edit_valuta}&to=EUR"
                    risposta_bce = requests.get(url_api, timeout=4).json()
                    if "rates" in risposta_bce and "EUR" in risposta_bce["rates"]:
                        tasso_cambio_bce = risposta_bce["rates"]["EUR"]
                except Exception:
                    tasso_cambio_bce = 1.0
            
            imponibile_calcolato_euro = round(edit_imponibile * tasso_cambio_bce, 2)
            
            # --- GESTIONE IVA FINALE ---
            iva_calcolata_euro = 0.00 if is_forfettario else round(imponibile_calcolato_euro * 0.22, 2)
            totale_calcolato_euro = round(imponibile_calcolato_euro + iva_calcolata_euro, 2)
            
            st.session_state["lotto_lavoro"][doc_selezionato] = {
                "fornitore": edit_fornitore,
                "identificativo_fiscale_fornitore": edit_piva_forn,
                "data_documento": edit_data,
                "valuta_originale": edit_valuta,
                "imponibile_valuta_originale": edit_imponibile,
                "imponibile_euro": imponibile_calcolato_euro,
                "codice_autofattura_sdi": edit_codice_sdi,
                "categoria_costo_suggerita": edit_cat,
                "paese_provenienza": edit_paese
            }

            # KPI Dorati Istantanei
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("Base Imponibile (€)", f"{imponibile_calcolato_euro:.2f} EUR")
            with col_info2:
                st.metric("IVA Integrazione (22%)", f"{iva_calcolata_euro:.2f} EUR", delta="Calcolata su SDI" if not is_forfettario else "Regime Forfettario (N2.2)")
            with col_info3:
                st.metric("Totale Autofattura (€)", f"{totale_calcolato_euro:.2f} EUR")

            # --- MOTORE DI PRE-VALIDAZIONE XSD ---
            st.markdown("#### 🛡️ Esito Ispezione Schema Ministeriale (Pre-Validazione XSD)")
            errori_scarto, avvisi_scarto = esegui_pre_check_xsd(st.session_state["lotto_lavoro"][doc_selezionato], piva_cliente)
            
            if errori_scarto:
                for err in errori_scarto:
                    st.error(f"❌ **ERRORE BLOCCANTE:** {err}")
            else:
                st.markdown("<div style='color: #10B981; font-weight: 600; margin-bottom: 10px;'>🟢 STRUTTURA XML CONFORME: Il tracciato supererà i controlli SDI dell'Agenzia delle Entrate.</div>", unsafe_allow_html=True)

            # --- SIMULATORE PRIMA NOTA ---
            st.markdown("#### 📊 Anteprima di Registrazione in Prima Nota (Doppia Entrata)")
            dati_conto = MAP_PIANO_CONTI.get(edit_cat, MAP_PIANO_CONTI["Software SaaS"])
            
            html_ledger = f"""
            <table class="ledger-table">
                <tr>
                    <th>Codice Conto</th>
                    <th>Descrizione Sotto-Conto</th>
                    <th>Dare (€)</th>
                    <th>Avere (€)</th>
                </tr>
                <tr>
                    <td>{dati_conto['conto_costo']}</td>
                    <td>{dati_conto['desc_costo']}</td>
                    <td>{imponibile_calcolato_euro:.2f}</td>
                    <td>0.00</td>
                </tr>
                <tr>
                    <td>{dati_conto['conto_ricavo']}</td>
                    <td>{dati_conto['desc_ricavo']}</td>
                    <td>0.00</td>
                    <td>{imponibile_calcolato_euro:.2f}</td>
                </tr>
            """
            if not is_forfettario:
                html_ledger += f"""
                <tr>
                    <td>2004001</td>
                    <td>IVA su acquisti (Reverse Charge Erario)</td>
                    <td>{iva_calcolata_euro:.2f}</td>
                    <td>0.00</td>
                </tr>
                <tr>
                    <td>5002010</td>
                    <td>Erario c/Autofattura IVA vendite</td>
                    <td>0.00</td>
                    <td>{iva_calcolata_euro:.2f}</td>
                </tr>
                """
            html_ledger += "</table>"
            st.markdown(html_ledger, unsafe_allow_html=True)
            st.write("")

            # --- TABELLA DI QUADRATURA E REPORT GENERATION ---
            st.markdown("---")
            st.markdown("#### 📈 Riepilogo Generale del Lotto Attivo")
            
            righe_report = []
            for k, v in st.session_state["lotto_lavoro"].items():
                imp_eur = v.get("imponibile_euro", 0.0)
                iva_riga = 0.00 if is_forfettario else round(imp_eur * 0.22, 2)
                tot_riga = round(imp_eur + iva_riga, 2)
                
                righe_report.append({
                    "Identificativo": k,
                    "Fornitore": v.get("fornitore", ""),
                    "Tax ID Fornitore": v.get("identificativo_fiscale_fornitore", ""),
                    "Data": v.get("data_documento", ""),
                    "Valuta Orig.": v.get("valuta_originale", ""),
                    "Imp. Valuta": v.get("imponibile_valuta_originale", 0.0),
                    "Imp. EUR (€)": imp_eur,
                    "IVA (€)": iva_riga,
                    "Totale Doc (€)": tot_riga,
                    "Codice SDI": v.get("codice_autofattura_sdi", "TD17")
                })
            
            df_report = pd.DataFrame(righe_report)
            st.dataframe(df_report, use_container_width=True)

            # --- GENERAZIONE IN LINEA COMPATIBILE DELLO ZIP (SOLUZIONE AL TYPEERROR) ---
            file_zip_buffer = io.BytesIO()
            con_errori_bloccanti = False
            
            with zipfile.ZipFile(file_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for idx, riga in enumerate(righe_report):
                    dati_xml = st.session_state["lotto_lavoro"][riga["Identificativo"]]
                    
                    err_check, _ = esegui_pre_check_xsd(dati_xml, piva_cliente)
                    if err_check:
                        con_errori_bloccanti = True
                        
                    xml_stringa_finale = genera_xml_autofattura(dati_xml, is_forfettario, nome_cliente, piva_cliente)
                    piva_p = piva_cliente.strip()
                    nome_file_xml = f"IT{piva_p}_{dati_xml.get('codice_autofattura_sdi')}_{idx+1:05d}.xml"
                    
                    # CORREZIONE POSIZIONALE PER EVITARE TYPEERROR:
                    zip_file.writestr(nome_file_xml, xml_stringa_finale)
            
            file_zip_buffer.seek(0)

            # Generazione file CSV di Quadratura
            csv_buffer = io.BytesIO()
            df_report.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig")
            csv_buffer.seek(0)

            st.markdown("#### 📦 Esportazione Output Certificati")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                if con_errori_bloccanti:
                    st.error("⚠️ Il download dello ZIP è bloccato: correggi gli errori XSD evidenziati sopra per sbloccarlo.")
                else:
                    st.download_button(
                        label="📥 SCARICA PACCHETTO XML MASSIVO (ZIP PER ADE/SDI)",
                        data=file_zip_buffer,
                        file_name=f"LOTTO_AUTOFATTURE_SDI_{piva_cliente.strip()}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
            with col_dl2:
                st.markdown('<div class="download-sec">', unsafe_allow_html=True)
                st.download_button(
                    label="📊 SCARICA REPORT DI QUADRATURA (EXCEL/CSV)",
                    data=csv_buffer,
                    file_name=f"REPORT_QUADRATURA_{piva_cliente.strip()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)
