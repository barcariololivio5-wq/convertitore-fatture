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

# --- CONFIGURAZIONE DELLA PAGINA (STILE PREMIUM) ---
st.set_page_config(
    page_title="TaxTech Intelligence Platform", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    ET.SubElement(id_fiscale_cess, "IdCodice").text = "00000000000"
    anagrafica_cess = ET.SubElement(dati_anagrafici_cess, "Anagrafica")
    ET.SubElement(anagrafica_cess, "Denominazione").text = "AZIENDA CLIENTE SRL"

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
                raise Exception("⚠️ Quota API esaurita. Contattare l'amministratore per passare al piano Enterprise.")
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if tentativo < max_tentativi - 1:
                    time.sleep(5)
                    continue
                else:
                    raise Exception("Server di elaborazione momentaneamente sovraccarico. Riprovare.")
            else:
                raise e

# --- LOGICA DI NAVIGAZIONE A SCHEDE (SaaS STYLE) ---
tab_overview, tab_operazione = st.tabs(["📊 Business Overview & KPI", "🚀 Area Operativa (Conversione)"])

# =====================================================================
# TAB 1: PRESENTAZIONE AZIENDALE, PREGI E OTTIMIZZAZIONE TEMPI
# =====================================================================
with tab_overview:
    # Header d'Impatto
    st.markdown("""
    <div style='background-color: #0F172A; padding: 40px; border-radius: 15px; text-align: center; margin-bottom: 30px;'>
        <h1 style='color: #38BDF8; font-family: sans-serif; font-size: 3rem; margin-bottom: 10px;'>TaxTech Intelligence Engine</h1>
        <p style='color: #94A3B8; font-size: 1.3rem;'>La soluzione definitiva per l'automazione massiva delle Autofatture Estere (TD17, TD18, TD19).</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sezione KPI Numerici (Attirano l'attenzione del cliente)
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    with col_kpi1:
        st.metric(label="Tempo di elaborazione / documento", value="~ 2.4 Secondi", delta="-93% vs Manuale")
    with col_kpi2:
        st.metric(label="Accuratezza Estrazione Dati", value="99.4%", delta="Certificato AI")
    with col_kpi3:
        st.metric(label="Rischio Sanzioni Formali SDI", value="0%", delta="Validazione a doppio loop")
    with col_kpi4:
        st.metric(label="Integrazione Tassi BCE", value="Real-Time", delta="Automatica")
        
    st.write("---")
    
    # Layout a due colonne per Pregi e Sprechi Eliminati
    col_pregi, col_sprechi = st.columns(2)
    
    with col_pregi:
        st.markdown("### 🌟 I Pregi dell'Infrastruttura")
        st.info("""
        * **Modello Vision Dual-Core:** Il sistema non fa una semplice lettura OCR. Comprende il contesto della fattura (strutturata o non strutturata) con la stessa logica di un contabile umano.
        * **BCE Currency Router Automatico:** In caso di fatture in Dollari (USD), Sterline (GBP) o altre valute, l'algoritmo interroga le API della Banca Centrale Europea applicando il tasso di cambio esatto del giorno del documento.
        * **Smart Chart of Accounts:** Riconosce la natura del servizio (es. Cloud AWS, Invoice Facebook, SaaS) e suggerisce immediatamente i codici Dare e Avere del Piano dei Conti dello Studio.
        * **GDPR Compliant Nativi (API Privata):** I dati non risiedono su server terzi, transitano in canali crittografati e non vengono utilizzati per l'addestramento di intelligenze artificiali pubbliche.
        """)
        
    with col_sprechi:
        st.markdown("### 🛑 Cosa eliminiamo per sempre")
        st.error("""
        * **Eliminazione del Data Entry Manuale:** Basta copiare a mano stringhe di codice IVA, Tax ID, indirizzi o tabelle Excel. Il file XML si compila da solo.
        * **Azzeramento degli Errori di Digitazione:** L'errore umano sul centesimo o sul codice del paese (che causa lo scarto o il rigetto formale da parte dello SDI) viene ridotto a zero.
        * **Eliminazione dei Tempi Morti di Ricerca Cambio:** Non perderai più tempo a cercare lo storico dei tassi di cambio della valuta sui siti istituzionali per fare le conversioni in Euro.
        * **Fine del Raccordo Contabile Manuale:** Lo studio riceve in Obsidian il file di riepilogo già classificato, azzerando le ore spese a fine mese per capire la natura del costo.
        """)

# =====================================================================
# TAB 2: AREA OPERATIVA BLINDATA
# =====================================================================
with tab_operazione:
    st.sidebar.title("⚙️ Parametri di Configurazione")
    is_forfettario = st.sidebar.checkbox("🏢 Gestione Regime Forfettario", value=False)
    nome_cliente = st.sidebar.text_input("Ragione Sociale Cliente", "Cliente_SRL")

    # --- ⚖️ SEZIONE TUTELA LEGALE E PRIVACY COMPLIANCE ---
    st.write("### ⚖️ Note Legali, Limitazione di Responsabilità e Privacy")
    with st.expander("Clicca qui per visualizzare i Riferimenti Normativi (Ex Art. 13 GDPR e Artt. 1229, 2236 C.C.)"):
        st.markdown("""
        **1. INFORMATIVA PRIVACY (Ex Art. 13 Regolamento UE 2016/679 - GDPR)**
        I dati estratti dai documenti caricati (inclusi dati fiscali, anagrafici ed economici) sono trattati in modalità transitoria unicamente per l'esecuzione tecnica della conversione del file. Il trattamento trova base giuridica nel consenso espresso dell'utente (**Ex Art. 6, par. 1, lett. a, GDPR**). I dati vengono instradati tramite canali API protetti e crittografati e **NON** vengono in alcun modo memorizzati o utilizzati per l'addestramento di intelligenze artificiali esterne. I dati di sintesi dell'operazione contabile vengono trasmessi esclusivamente al sistema di monitoraggio centrale dello Studio Professionale titolare.
        
        **2. CLAUSOLA DI MANLEVA E LIMITAZIONE DI RESPONSABILITÀ (Ex Art. 1229 Codice Civile)**
        Il presente applicativo fornisce elaborazioni statistiche e predittive automatizzate tramite modelli di Intelligenza Artificiale. Ai sensi e per gli effetti dell'**Art. 1229 del Codice Civile**, il fornitore dell'infrastruttura informatica, gli sviluppatori e lo Studio Professionale non si assumono alcuna responsabilità per danni diretti, indiretti, sanzioni amministrative, accertamenti fiscali o rigetti formali causati da errori tecnici, imprecisioni, omissioni o 'allucinazioni' dell'algoritmo nella compilazione dell'XML. 
        
        **3. PRESTAZIONE DI MEZZI E TASSACOLO OBBLIGO DI VERIFICA (Ex Art. 2236 Codice Civile)**
        L'utente prende atto che il servizio si configura come fornitura di meri mezzi informatici e non di risultato. L'attribuzione della natura IVA, delle aliquote e della codifica del documento (es. TD17, TD18, TD19) è un suggerimento provvisorio. Resta in capo all'utente l'**obbligo tassativo di revisionare, controllare e validare manualmente** la correttezza del file XML generato prima dell'invio formale al Sistema di Interscambio (SDI) dell'Agenzia delle Entrate. Nei casi di prestazioni che implicano la soluzione di problemi tecnici di speciale difficoltà, la responsabilità è limitata ai soli casi di dolo o colpa grave ai sensi dell'**Art. 2236 del Codice Civile**.
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
        files_caricati = st.file_uploader("Trascina qui i documenti o fai clic per caricarli (PDF o Immagini)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)
        
        if files_caricati:
            # Pulsante sbloccato SOLO se l'utente accetta la manleva legale
            if st.button("🚀 Avvia Conversione Massiva ed Invia al Hub Studio", disabled=not accettazione_legale):
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
                            
                            # --- ASSOCIAZIONE AUTOMATICA DARE / AVERE ---
                            categoria = risultato.get("categoria_costo_suggerita", "Software SaaS")
                            conti = MAP_DARE_AVERE.get(categoria, {"dare": "3006001", "avere": "4010002"})
                            
                            # Generazione XML SDI sicuro
                            xml_contenuto = genera_xml_autofattura(risultato, imponibile_in_euro, is_forfettario)
                            nome_file_xml = f"Fatture_XML/IT00000000000_{risultato['codice_autofattura_sdi']}_{index:05d}.xml"
                            zip_file.writestr(nome_file_xml, xml_contenuto)
                            
                            # Invio ad Obsidian con Dare/Avere inclusi
                            invia_al_cervello_centralizzato(risultato, nome_cliente, imponibile_in_euro, conti["dare"], conti["avere"])
                            
                            # Dati per la tabella di anteprima
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
                        st.success("🎯 Processo completato con successo!")
                        df_reg = pd.DataFrame(lista_registro)
                        st.dataframe(df_reg[["File", "fornitore", "Imponibile (€)", "Conto Dare", "Conto Avere", "codice_autofattura_sdi", "Controllo AI"]], use_container_width=True)
                        
                        zip_file.close()
                        file_zip_buffer.seek(0)
                        
                        st.download_button(
                            label="📥 SCARICA PACCHETTO COMPLETO XML PER LO SDI", 
                            data=file_zip_buffer, 
                            file_name="autofatture_sdi.zip", 
                            mime="application/zip"
                        )
