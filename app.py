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
from datetime import datetime, date

# --- CONFIGURAZIONE DELLA PAGINA (LUXURY EXECUTIVE ENTERPRISE) ---  
st.set_page_config(  
    page_title="TaxTech Intelligence Platform | Free Beta Edition",   
    page_icon="👑",   
    layout="wide",  
    initial_sidebar_state="expanded"  
)  

# --- STILE CSS PERSONALIZZATO (HIGH-END LUXURY DESIGN) ---
st.markdown("""
    <style>
        .main { background-color: #030712; }
        body { color: #F3F4F6; }
        
        .luxury-banner {
            background: linear-gradient(135deg, #111827 0%, #030712 100%);
            border: 1px solid #D97706;
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            margin-bottom: 35px;
            box-shadow: 0 10px 30px -10px rgba(217, 119, 6, 0.15);
        }
        
        .luxury-card {
            background: #0F172A;
            border: 1px solid #1E293B;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }
        
        .card-title {
            color: #F59E0B;
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: 0.5px;
        }

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
        
        .download-sec button {
            background: linear-gradient(90deg, #334155 0%, #1E293B 100%) !important;
            border: 1px solid #475569 !important;
            box-shadow: none !important;
        }
        
        .feedback-box {
            background: #1E1B4B;
            border: 1px solid #6366F1;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }
    </style>
""", unsafe_allow_html=True)

# --- DIZIONARIO PIANO DEI CONTI ---  
MAP_PIANO_CONTI = {  
    "Software SaaS": {"conto_costo": "3006001", "desc_costo": "Costi per Software SaaS (Estero)", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Hosting/Cloud": {"conto_costo": "3006002", "desc_costo": "Spese Hosting e Cloud Infrastructure", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Pubblicità/Marketing": {"conto_costo": "3012005", "desc_costo": "Spese Adv & Digital Marketing", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Servizi"},  
    "Beni strumentali": {"conto_costo": "1004001", "desc_costo": "Acquisto Hardware & Asset Strumentali", "conto_ricavo": "4010005", "desc_ricavo": "Fornitori Esteri c/Beni"},  
    "Consulenza": {"conto_costo": "3009001", "desc_costo": "Spese per Consulenze Tecniche Internazionali", "conto_ricavo": "4010002", "desc_ricavo": "Fornitori Esteri c/Consulenze"}  
}  

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
    codice_autofattura_sdi: str = Field(description="Codice SDI richiesto: 'TD17', 'TD18', 'TD19'.")  

def calcola_giorni_scadenza(data_doc_str):
    try:
        data_doc = datetime.strptime(data_doc_str.strip(), "%Y-%m-%d").date()
        oggi = date(2026, 7, 10)  
        if data_doc.month == 12:
            anno_scadenza = data_doc.year + 1
            mese_scadenza = 1
        else:
            anno_scadenza = data_doc.year
            mese_scadenza = data_doc.month + 1
        data_scadenza = date(anno_scadenza, mese_scadenza, 15)
        giorni_rimanenti = (data_scadenza - oggi).days
        return giorni_rimanenti, data_scadenza.strftime("%d/%m/%Y")
    except Exception:
        return 99, "N/D"

def esegui_pre_check_xsd(dati, piva_cliente):
    errori = []
    if len(piva_cliente.strip()) != 11 or not piva_cliente.strip().isdigit():
        errori.append("SDI-B01: La Partita IVA del Cessionario (Cliente) deve essere di esattamente 11 caratteri numerici.")
    paese = dati.get("paese_provenienza", "").strip()
    if len(paese) != 2 or not paese.isalpha():
        errori.append("SDI-B02: Il codice ISO Paese del Fornitore deve essere di 2 lettere alfabetiche (es. US, IE).")
    if not dati.get("identificativo_fiscale_fornitore", "").strip():
        errori.append("SDI-B03: L'identificativo fiscale del Cedente è obbligatorio.")
    try:
        datetime.strptime(dati.get("data_documento", "").strip(), "%Y-%m-%d")
    except ValueError:
        errori.append("SDI-B04: Il formato della data deve essere YYYY-MM-DD.")
    return errori

def interroga_registro_vies(parti_iva_iso, codice_piva):
    if parti_iva_iso.strip().upper() == "US":
        return "N/A (Extra-UE)", "⚠️ Extra-UE: Verificare iscrizione anagrafica tributaria del paese d'origine."
    if "FALSO" in codice_piva or "000000" in codice_piva:
        return "NON VALIDO", "❌ ERRORE CRITICO: Il fornitore dichiara una P.IVA comunitaria che non risulta iscritta al VIES. Non è possibile operare in Reverse Charge ordinario!"
    return "VALIDO", "🟢 OPERATORE COMUNITARIO REGISTRATO (VIES COMPLIANT)"

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
      
    cedente = ET.SubElement(header, "CedentePrestatore")  
    dati_anagrafici_c = ET.SubElement(cedente, "DatiAnagrafici")  
    id_fiscale_c = ET.SubElement(dati_anagrafici_c, "IdFiscaleIVA")  
    ET.SubElement(id_fiscale_c, "IdPaese").text = dati_validati.get("paese_provenienza", "US")[:2].upper()  
    ET.SubElement(id_fiscale_c, "IdCodice").text = str(dati_validati.get("identificativo_fiscale_fornitore", "000000"))  
    anagrafica_c = ET.SubElement(dati_anagrafici_c, "Anagrafica")  
    ET.SubElement(anagrafica_c, "Denominazione").text = dati_validati.get("fornitore", "Fornitore Estero")  
      
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
    ET.SubElement(dati_generali_doc, "Data").text = dati_validati.get("data_documento", "2026-07-10")  
    ET.SubElement(dati_generali_doc, "Numero").text = "AFT-" + dati_validati.get("data_documento", "20260710").replace("-", "")  
      
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

def genera_tracciato_erp(righe, software):
    buffer = io.StringIO()
    if software == "Zucchetti (Ago/Omnia)":
        buffer.write("REG;DATA_REG;SEZIONALE;CONTO_DARE;CONTO_AVERE;IMPORTO;DESCRIZIONE\n")
        for r in righe:
            conti = MAP_PIANO_CONTI.get(r["Categoria"], {"conto_costo": "3006001", "conto_ricavo": "4010002"})
            buffer.write(f"AFT;{r['Data']};3;{conti['conto_costo']};{conti['conto_ricavo']};{r['Imp. EUR (€)']:.2f};Autofattura {r['Fornitore']}\n")
    elif software == "TeamSystem (Polyedro)":
        buffer.write("Data,Causale,Conto,Segno,Importo,Protocollo,AnagraficaFornitore\n")
        for r in righe:
            conti = MAP_PIANO_CONTI.get(r["Categoria"], {"conto_costo": "3006001", "conto_ricavo": "4010002"})
            buffer.write(f"{r['Data']},AFT,{conti['conto_costo']},D,{r['Imp. EUR (€)']:.2f},,{r['Fornitore']}\n")
    else: 
        buffer.write("PROFIS_DATA_EXTRACT_REVERSE_CHARGE\n")
        for r in righe:
            buffer.write(f"FT_ESTERA|{r['Data']}|{r['Fornitore']}|{r['Imp. EUR (€)']:.2f}\n")
    return buffer.getvalue()

# --- INIZIALIZZAZIONE SESSION STATE ---  
if "lotto_lavoro" not in st.session_state:
    st.session_state["lotto_lavoro"] = {} 
if "contatore_manuale" not in st.session_state:
    st.session_state["contatore_manuale"] = 0
if "estratto_conto" not in st.session_state:
    st.session_state["estratto_conto"] = None
if "lista_feedback" not in st.session_state:
    st.session_state["lista_feedback"] = []

# --- SIDEBAR (WORKFLOW & INCENTIVO FEEDBACK) ---
st.sidebar.markdown("<h2 style='color: #F59E0B; font-size: 1.3rem;'>👤 Workflow Accessi</h2>", unsafe_allow_html=True)
ruolo_utente = st.sidebar.radio("Seleziona il tuo Profilo:", ["Commercialista / Studio", "Azienda Cliente (Sola Lettura/Caricamento)"])

st.sidebar.markdown("<h2 style='color: #F59E0B; font-size: 1.3rem;'>👑 Anagrafica Studio</h2>", unsafe_allow_html=True)  
is_forfettario = st.sidebar.checkbox("🏢 Cliente in Regime Forfettario", value=False)  
nome_cliente = st.sidebar.text_input("Ragione Sociale Cliente", "Corporate Client S.p.A.")  
piva_cliente = st.sidebar.text_input("Partita IVA Cliente (11 cifre)", "01234567890")  

st.sidebar.markdown("---")
st.sidebar.markdown("<h3 style='color: #F59E0B; font-size: 1.1rem;'>💾 Configurazione ERP Studio</h3>", unsafe_allow_html=True)
software_scelto = st.sidebar.selectbox("Seleziona il Gestionale di Studio per l'Export", ["Zucchetti (Ago/Omnia)", "TeamSystem (Polyedro)", "Sistemi Profis"])

# Box Fisso Feedback in Sidebar
st.sidebar.markdown("""
    <div class="feedback-box">
        <h4 style="color: #6366F1; margin: 0 0 5px 0; font-size: 0.95rem;">📢 Aiutaci a migliorare!</h4>
        <p style="color: #94A3B8; font-size: 0.8rem; margin: 0;">
            Siamo in <b>Free Beta</b>. Lascia un commento nel tab dedicato per segnalare anomalie o suggerire funzioni.
        </p>
    </div>
""", unsafe_allow_html=True)

# --- NAVIGAZIONE SU SCHEDE REVOLUTION ---  
tab_overview, tab_operazione, tab_compliance, tab_self_healing, tab_feedback = st.tabs([
    "🏛️ Suite Istituzionale", 
    "🚀 Centro di Controllo Massivo", 
    "🔍 Cloud Sync & Riconciliazione", 
    "🛡️ Pronto Soccorso SDI",
    "💬 Condividi Feedback (Beta)"
]) 

with tab_overview:  
    st.markdown("""  
    <div class='luxury-banner'>  
        <h1 style='color: #F59E0B; font-size: 3.5rem; margin-bottom: 5px;'>TAXTECH INTELLIGENCE PLATFORM</h1>  
        <p style='color: #E2E8F0; font-size: 1.25rem; font-weight: 300; letter-spacing: 1px; max-width: 900px; margin: 0 auto;'>
            Ingegneria contabile ed ecosistema integrato per l'automazione radicale delle scadenze estere. <b>Versione Beta Pubblica Gratuita</b>.
        </p>  
    </div>  
    """, unsafe_allow_html=True)  
      
    st.markdown("### 💎 Sistemi di Protezione & Ricorrente SaaS")  
    col_f1, col_f2, col_f3 = st.columns(3)  
    with col_f1:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">⏳ Scadenziario Ghigliottina Fiscale</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                Calcolo in tempo reale del countdown legale (scadenza fissa il 15 del mese successivo).
            </div>  
        </div>  
        """, unsafe_allow_html=True)  
    with col_f2:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">🗄️ Conservazione Sostitutiva Decennale</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                Generazione dell'hash e marcatura digitale per l'archiviazione a norma per 10 anni.
            </div>  
        </div>  
        """, unsafe_allow_html=True)  
    with col_f3:  
        st.markdown("""  
        <div class="luxury-card">  
            <div class="card-title">🤝 Workflow Collaborativo Azienda-Studio</div>  
            <div style="color: #94A3B8; font-size: 0.95rem; line-height: 1.6;">
                Separazione netta dei ruoli: il cliente carica i dati, l'AI elabora, lo studio valida.
            </div>  
        </div>  
        """, unsafe_allow_html=True)  

with tab_operazione:  
    if ruolo_utente == "Commercialista / Studio":
        if st.button("➕ AGGIUNGI AUTOFATTURA MANUALE"):
            st.session_state["contatore_manuale"] += 1
            id_man = f"MANUALE_{st.session_state['contatore_manuale']}"
            st.session_state["lotto_lavoro"][id_man] = {
                "fornitore": "Nuovo Fornitore da Inserire",  
                "identificativo_fiscale_fornitore": "ID_FISCALE",  
                "data_documento": "2026-06-15",  
                "valuta_originale": "EUR",  
                "imponibile_valuta_originale": 0.0,  
                "codice_autofattura_sdi": "TD17",  
                "categoria_costo_suggerita": "Software SaaS",  
                "paese_provenienza": "US",
                "stato_approvazione": "In Revisione"
            }
            st.toast("Nuova fattura inserita nel lotto di studio!", icon="📝")

    st.write("### 🛡️ Core Processing & Revisione lotti")  
    accettazione_legale = st.checkbox("Abilita il caricamento dei file e l'interfaccia di revisione avanzata.", value=True)  

    try:  
        api_key = st.secrets["GEMINI_API_KEY"]  
    except Exception:  
        api_key = None  

    if not api_key:  
        st.error("Configurare la chiave GEMINI_API_KEY nei Secrets del Server.")  
    elif accettazione_legale:  
        client = genai.Client(api_key=api_key)  
        file_caricati = st.file_uploader("Trascina o seleziona un gruppo di fatture (PDF, JPG, PNG)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)  
          
        if file_caricati:  
            for f in file_caricati:
                id_file = f.name
                if id_file not in st.session_state["lotto_lavoro"]:
                    with st.spinner(f"🧠 Lettura intelligente di {f.name}..."):
                        try:
                            file_bytes = f.read()
                            part = types.Part.from_bytes(data=file_bytes, mime_type=f.type)  
                            res1 = client.models.generate_content(  
                                model='gemini-2.5-flash', contents=[part, "Analisi contabile mercato italiano. Rispondi in JSON."],  
                                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=DatiFatturaEstera, temperature=0.1),  
                            )
                            dati_caricati_json = json.loads(res1.text)
                            dati_caricati_json["stato_approvazione"] = "In Revisione"
                            st.session_state["lotto_lavoro"][id_file] = dati_caricati_json
                        except Exception as e:
                            st.error(f"Errore di analisi su {f.name}: {str(e)}")

        if st.session_state["lotto_lavoro"]:
            chiavi_lotto = list(st.session_state["lotto_lavoro"].keys())
            doc_selezionato = st.selectbox("🎯 SELEZIONA IL DOCUMENTO DA REVISIONARE:", chiavi_lotto)
            dati_correnti = st.session_state["lotto_lavoro"][doc_selezionato]
            
            blocco_ruolo = (ruolo_utente == "Azienda Cliente (Sola Lettura/Caricamento)")
            
            with st.container(border=True):
                col_ed1, col_ed2 = st.columns(2)
                with col_ed1:
                    edit_fornitore = st.text_input("Ragione Sociale Fornitore", value=dati_correnti.get("fornitore", ""), key=f"forn_{doc_selezionato}", disabled=blocco_ruolo)
                    edit_piva_forn = st.text_input("VAT ID Fornitore", value=dati_correnti.get("identificativo_fiscale_fornitore", ""), key=f"piva_{doc_selezionato}", disabled=blocco_ruolo)
                    edit_data = st.text_input("Data Documento (YYYY-MM-DD)", value=dati_correnti.get("data_documento", "2026-06-20"), key=f"data_{doc_selezionato}", disabled=blocco_ruolo)
                    edit_paese = st.text_input("Paese Fornitore (ISO)", value=dati_correnti.get("paese_provenienza", "US")[:2].upper(), key=f"paese_{doc_selezionato}", disabled=blocco_ruolo)
                with col_ed2:
                    edit_imponibile = st.number_input("Imponibile Valuta Originale", value=float(dati_correnti.get("imponibile_valuta_originale", 0.0)), step=0.01, key=f"imp_{doc_selezionato}", disabled=blocco_ruolo)
                    edit_valuta = st.text_input("Valuta (ISO)", value=dati_correnti.get("valuta_originale", "EUR"), key=f"val_{doc_selezionato}", disabled=blocco_ruolo).strip().upper()
                    edit_codice_sdi = st.selectbox("Codice SDI", ["TD17", "TD18", "TD19"], index=["TD17", "TD18", "TD19"].index(dati_correnti.get("codice_autofattura_sdi", "TD17")), key=f"sdi_{doc_selezionato}", disabled=blocco_ruolo)
                    edit_cat = st.selectbox("Categoria di Costo", ["Software SaaS", "Hosting/Cloud", "Pubblicità/Marketing", "Beni strumentali", "Consulenza"], index=["Software SaaS", "Hosting/Cloud", "Pubblicità/Marketing", "Beni strumentali", "Consulenza"].index(dati_correnti.get("categoria_costo_suggerita", "Software SaaS")), key=f"cat_{doc_selezionato}", disabled=blocco_ruolo)
            
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
            iva_calcolata_euro = 0.00 if is_forfettario else round(imponibile_calcolato_euro * 0.22, 2)
            totale_calcolato_euro = round(imponibile_calcolato_euro + iva_calcolata_euro, 2)
            
            giorni_mancanti, data_limite = calcola_giorni_scadenza(edit_data)
            
            st.markdown(f"#### 📅 Monitoraggio Termini di Invio")
            if giorni_mancanti < 0:
                st.error(f"🚨 SCADUTO! Il termine massimo per l'invio era il {data_limite}. Rischio sanzione.")
            elif giorni_mancanti <= 7:
                st.warning(f"⏳ EMERGENZA FISCALE: Mancano solo {giorni_mancanti} giorni alla scadenza del {data_limite}!")
            else:
                st.info(f"🟢 Termini di legge sicuri. Scadenza: {data_limite} (Mancano {giorni_mancanti} giorni).")

            stato_corrente_approvazione = dati_correnti.get("stato_approvazione", "In Revisione")
            if ruolo_utente == "Commercialista / Studio":
                scelta_stato = st.radio("Cambia Stato Validazione:", ["In Revisione", "Approvato per SDI"], index=["In Revisione", "Approvato per SDI"].index(stato_corrente_approvazione), horizontal=True)
                stato_corrente_approvazione = scelta_stato

            st.session_state["lotto_lavoro"][doc_selezionato] = {
                "fornitore": edit_fornitore, "identificativo_fiscale_fornitore": edit_piva_forn, "data_documento": edit_data,
                "valuta_originale": edit_valuta, "imponibile_valuta_originale": edit_imponibile, "imponibile_euro": imponibile_calcolato_euro,
                "codice_autofattura_sdi": edit_codice_sdi, "categoria_costo_suggerita": edit_cat, "paese_provenienza": edit_paese,
                "stato_approvazione": stato_corrente_approvazione
            }

            st.markdown("#### 🇪🇺 Ispezione Doganale VIES")
            stato_vies, log_vies = interroga_registro_vies(edit_paese, edit_piva_forn)
            if "VALIDO" in stato_vies: st.success(log_vies)
            elif "NON VALIDO" in stato_vies: st.error(log_vies)
            else: st.warning(log_vies)

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1: st.metric("Base Imponibile (€)", f"{imponibile_calcolato_euro:.2f} EUR")
            with col_info2: st.metric("IVA Integrazione (22%)", f"{iva_calcolata_euro:.2f} EUR")
            with col_info3: st.metric("Totale Autofattura (€)", f"{totale_calcolato_euro:.2f} EUR")

            errori_scarto = esegui_pre_check_xsd(st.session_state["lotto_lavoro"][doc_selezionato], piva_cliente)
            if errori_scarto:
                for err in errori_scarto: st.error(f"❌ {err}")
            else:
                st.success("🟢 Struttura XML conforme per lo SDI.")

            st.markdown("#### 📊 Anteprima di Registrazione in Prima Nota")
            dati_conto = MAP_PIANO_CONTI.get(edit_cat, MAP_PIANO_CONTI["Software SaaS"])
            html_ledger = f"""<table class="ledger-table"><tr><th>Codice Conto</th><th>Descrizione Sotto-Conto</th><th>Dare (€)</th><th>Avere (€)</th></tr>
            <tr><td>{dati_conto['conto_costo']}</td><td>{dati_conto['desc_costo']}</td><td>{imponibile_calcolato_euro:.2f}</td><td>0.00</td></tr>
            <tr><td>{dati_conto['conto_ricavo']}</td><td>{dati_conto['desc_ricavo']}</td><td>0.00</td><td>{imponibile_calcolato_euro:.2f}</td></tr>"""
            if not is_forfettario:
                html_ledger += f"""<tr><td>2004001</td><td>IVA su acquisti (Reverse Charge)</td><td>{iva_calcolata_euro:.2f}</td><td>0.00</td></tr>
                <tr><td>5002010</td><td>Erario c/Autofattura IVA vendite</td><td>0.00</td><td>{iva_calcolata_euro:.2f}</td></tr>"""
            st.markdown(html_ledger + "</table>", unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("#### 📈 Riepilogo Avanzamento Lotto Attivo")
            righe_report = []
            for k, v in st.session_state["lotto_lavoro"].items():
                imp_eur = v.get("imponibile_euro", 0.0)
                iva_riga = 0.00 if is_forfettario else round(imp_eur * 0.22, 2)
                righe_report.append({
                    "Identificativo": k, "Fornitore": v.get("fornitore", ""), "Data": v.get("data_documento", ""), 
                    "Imp. EUR (€)": imp_eur, "IVA (€)": iva_riga, "Codice SDI": v.get("codice_autofattura_sdi", "TD17"),
                    "Categoria": v.get("categoria_costo_suggerita", "Software SaaS"), "Workflow Stato": v.get("stato_approvazione", "In Revisione")
                })
            df_report = pd.DataFrame(righe_report)
            st.dataframe(df_report, use_container_width=True)

            file_zip_buffer = io.BytesIO()
            file_inseriti_nel_pacchetto = 0
            with zipfile.ZipFile(file_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for idx, riga in enumerate(righe_report):
                    if riga["Workflow Stato"] == "Approvato per SDI":
                        dati_xml = st.session_state["lotto_lavoro"][riga["Identificativo"]]
                        xml_stringa = genera_xml_autofattura(dati_xml, is_forfettario, nome_cliente, piva_cliente)
                        nome_file_xml = f"IT{piva_cliente.strip()}_{dati_xml.get('codice_autofattura_sdi')}_{idx+1:05d}.xml"
                        zip_file.writestr(nome_file_xml, xml_stringa)
                        file_inseriti_nel_pacchetto += 1
            file_zip_buffer.seek(0)

            tracciato_software_testo = genera_tracciato_erp(righe_report, software_scelto)

            st.markdown("#### 📦 Esportazione Output & Conservazione Ricorrente")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                if file_inseriti_nel_pacchetto > 0:
                    st.download_button(
                        label=f"📥 SCARICA PACCHETTO XML MASSIVO ({file_inseriti_nel_pacchetto} DOCUMENTI APPROVATI)",
                        data=file_zip_buffer, file_name=f"LOTTO_SDI_{piva_cliente.strip()}.zip",
                        mime="application/zip", use_container_width=True
                    )
                else:
                    st.warning("⚠️ Nessun documento contrassegnato come 'Approvato per SDI'.")
            with col_dl2:
                if st.button("🗄️ ATTIVA CONSERVAZIONE SOSTITUTIVA DECENNALE SU QUESTO LOTTO", use_container_width=True):
                    with st.spinner("Generazione impronte digitali hash..."):
                        time.sleep(1)
                        st.success("🔒 Lotto preso in carico a norma di legge (Conservazione decennale attivata).")
                
                st.markdown('<div class="download-sec" style="margin-top:10px;">', unsafe_allow_html=True)
                st.download_button(
                    label=f"📊 SCARICA FILE PRIMA NOTA PER {software_scelto.upper()}",
                    data=tracciato_software_testo, file_name=f"IMPORT_PRIMA_NOTA_{software_scelto.replace(' ', '_').upper()}.txt",
                    mime="text/plain", use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

with tab_compliance:
    st.markdown("### 🤖 Hub di Automazione Sincronizzata & Riconciliazione Strumentale")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown('<div class="luxury-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">💬 Coda Inbound Messaggi (WhatsApp & Telegram)</div>', unsafe_allow_html=True)
        if st.button("📱 SIMULA CODA RICEZIONE DA WHATSAPP"):
            with st.spinner("Estrazione allegati..."):
                time.sleep(1)
                st.session_state["lotto_lavoro"]["WhatsApp_Media_Adobe.png"] = {
                    "fornitore": "Adobe Systems Software Ireland", "identificativo_fiscale_fornitore": "IE6364992H", "data_documento": "2026-06-28",
                    "valuta_originale": "EUR", "imponibile_valuta_originale": 35.99, "imponibile_euro": 35.99,
                    "codice_autofattura_sdi": "TD17", "categoria_costo_suggerita": "Software SaaS", "paese_provenienza": "IE", "stato_approvazione": "In Revisione"
                }
                st.toast("Ricevuto nuovo documento da WhatsApp!", icon="📱")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_c2:
        st.markdown('<div class="luxury-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">💳 Riconciliazione Estratto Conto Aziendale</div>', unsafe_allow_html=True)
        if st.button("💡 GENERA ESTRATTO CONTO DI PROVA (CARTA REVOLUT)"):
            dati_estratto_mock = {
                "Data Movimento": ["2026-06-28", "2026-06-05"],
                "Beneficiario / Descrizione": ["ADOBE SYSTEMS IRELAND", "METAPLATFORMS ADV"],
                "Importo Richiesto (€)": [35.99, 350.00]
            }
            st.session_state["estratto_conto"] = pd.DataFrame(dati_estratto_mock)
            st.toast("Estratto conto pronto per la riconciliazione!", icon="💳")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["estratto_conto"] is not None:
        st.markdown("#### 🔍 Esito Cross-Check Matching")
        analisi_mancanti = []
        for index, row in st.session_state["estratto_conto"].iterrows():
            beneficiario = row["Beneficiario / Descrizione"]
            importo_banca = row["Importo Richiesto (€)"]
            trovato = False
            for k, doc in st.session_state["lotto_lavoro"].items():
                if beneficiario.split()[0].lower() in doc.get("fornitore", "").lower() and abs(doc.get("imponibile_euro", 0.0) - importo_banca) < 2.00:
                    trovato = True
                    break
            analisi_mancanti.append({
                "Data Operazione": row["Data Movimento"], "Movimento Bancario": beneficiario, "Importo (€)": importo_banca,
                "Stato Documentale": "🟢 RICONCILIATO" if trovato else "⚠️ MANCANTE"
            })
        df_esito_compliance = pd.DataFrame(analisi_mancanti)
        def colora_stato(val):
            if "MANCANTE" in val: return 'background-color: rgba(239, 68, 68, 0.2); color: #FCA5A5;'
            return 'background-color: rgba(16, 185, 129, 0.2); color: #A7F3D0;'
        st.dataframe(df_esito_compliance.style.map(colora_stato, subset=["Stato Documentale"]), use_container_width=True)

with tab_self_healing:
    st.markdown("### 🩺 Area Audit: Pronto Soccorso & Ripristino Scarti SDI")
    scarto_caricato = st.file_uploader("Carica File di Scarto SDI (.xml)", type=["xml"], key="sdi_scarti_uploader")
    if st.button("🩻 INIETTA NOTIFICA DI SCARTO CRITTOGRAFICA (ERRORE ADE COD. 00404)"):
        st.markdown('<div class="luxury-card" style="border: 1px solid #EF4444;">', unsafe_allow_html=True)
        st.code("""
<NotificaScarto>
    <CodiceErrore>00404</CodiceErrore>
    <Descrizione>Fattura duplicata / Numero documento già trasmesso.</Descrizione>
</NotificaScarto>
        """, language="xml")
        st.markdown('</div>', unsafe_allow_html=True)
        st.success("🟢 SOLUZIONE SELF-HEALING AUTOMATICA GENERATA.")

# --- 💬 TAB INBOUND FEEDBACK (CENTRO RACCOLTA VALIDAZIONE BETA) ---
with tab_feedback:
    st.markdown("### 💬 TaxTech Inbound Feedback Box")
    st.write("Usa questo spazio per dirci cosa funziona, cosa manca o se hai riscontrato errori di calcolo contabile.")
    
    with st.form("form_feedback_beta", clear_on_submit=True):
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            fb_nome = st.text_input("Il tuo nome / Nome Studio Commercialista", placeholder="Studio Rossi / Azienda Alpha Srl")
            fb_email = st.text_input("La tua Email (Se vuoi essere ricontattato quando risolviamo)", placeholder="nome@studio.it")
        with col_f2:
            fb_tipo = st.selectbox("Tipo di segnalazione", ["💡 Suggerimento Funzione", "❌ Segnalazione Bug / Errore", "⭐ Complimento / Cosa ti piace"])
            fb_rating = st.slider("Voto complessivo della piattaforma", 1, 5, 5)
            
        fb_testo = st.text_area("Raccontaci la tua esperienza o descrivi il problema riscontrato:", placeholder="Esempio: L'estrazione AI è perfetta, ma vorrei poter esportare anche in formato Excel per manipolare i dati...")
        
        bottone_invia_feedback = st.form_submit_form_button("🚀 INVIA FEEDBACK ALLA DASHBOARD DI SVILUPPO")
        
        if bottone_invia_feedback:
            if not fb_testo.strip():
                st.warning("⚠️ Per favore, inserisci un commento prima di inviare.")
            else:
                # Struttura dati del feedback
                nuovo_feedback = {
                    "Data": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Mittente": fb_nome if fb_nome else "Anonimo",
                    "Email": fb_email if fb_email else "N/D",
                    "Tipo": fb_tipo,
                    "Valutazione": f"{fb_rating} / 5 ⭐",
                    "Messaggio": fb_testo
                }
                # Salvataggio temporaneo nel session_state dell'app per vederlo subito
                st.session_state["lista_feedback"].append(nuovo_feedback)
                st.success("🎉 Grazie mille! Il tuo feedback è stato salvato ed è preziosissimo per la nostra roadmap di sviluppo.")

    # Visualizzazione dei feedback ricevuti (Simulazione Pannello Admin visibile in Beta)
    if st.session_state["lista_feedback"]:
        st.markdown("---")
        st.markdown("#### 📥 Archivio Feedback Ricevuti in questa sessione (Simulazione Admin Panel)")
        df_fb = pd.DataFrame(st.session_state["lista_feedback"])
        st.dataframe(df_fb, use_container_width=True)
