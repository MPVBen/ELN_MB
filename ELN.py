import streamlit as st
import os
import json
import base64
import tempfile
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

st.set_page_config(page_title="Cahier de Labo", page_icon="🧪", layout="wide")

# --- 🔒 1. SYSTÈME DE SÉCURITÉ ---
if "authentifie" not in st.session_state:
    st.session_state.authentifie = False

if not st.session_state.authentifie:
    st.title("🔒 Accès Sécurisé au Cahier de Labo")
    mdp_saisi = st.text_input("Veuillez entrer le mot de passe :", type="password")
    
    if st.button("Se connecter"):
        if mdp_saisi == st.secrets["MOT_DE_PASSE_APP"]:
            st.session_state.authentifie = True
            st.rerun()
        else:
            st.error("❌ Mot de passe incorrect.")
    st.stop()

# --- ☁️ 2. CONNEXION À GOOGLE DRIVE ---
@st.cache_resource
def get_drive_service():
    creds_info = json.loads(st.secrets["TOKEN_GCP"])
    creds = Credentials.from_authorized_user_info(
        creds_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

service = get_drive_service()
DOSSIER_RACINE_ID = st.secrets["DOSSIER_RACINE_ID"]

def get_or_create_folder(folder_name, parent_id):
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    else:
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def upload_file(file_path, file_name, parent_id, mime_type='application/octet-stream'):
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    file_metadata = {'name': file_name, 'parents': [parent_id]}
    query = f"name='{file_name}' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    items = results.get('files', [])
    if items:
        file_id = items[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()

# --- 🧠 3. GESTION DE L'HISTORIQUE ---
NOM_FICHIER_HISTO = "historique_labo.json"

def charger_historique_drive():
    query = f"name='{NOM_FICHIER_HISTO}' and '{DOSSIER_RACINE_ID}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    items = results.get('files', [])
    if items:
        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return json.loads(fh.getvalue().decode('utf-8'))
    return {"appareils": [], "calibrations": [], "reactifs": []}

if "historique" not in st.session_state:
    with st.spinner("Connexion au Drive et chargement de la mémoire..."):
        try:
            st.session_state.historique = charger_historique_drive()
        except Exception as e:
            st.warning("⚠️ Délai d'attente dépassé pour le Drive, utilisation d'un historique vide pour l'instant.")
            st.session_state.historique = {"appareils": [], "calibrations": [], "reactifs": []}

historique = st.session_state.historique


# ==========================================
# 🚀 DÉBUT DE L'INTERFACE AVEC ONGLETS
# ==========================================
st.title("🧪 Cahier de Labo Électronique")

# Création des deux onglets
tab_nouvelle, tab_recherche = st.tabs(["📝 Nouvelle Manip", "🔍 Rechercher une manip"])

# ---------------------------------------------------------
# ONGLET 2 : LA BARRE DE RECHERCHE
# ---------------------------------------------------------
with tab_recherche:
    st.markdown("### 🔍 Retrouver une ancienne manipulation")
    st.write("Recherche dans tes dossiers sur Google Drive par Code Manip, Titre ou Date.")
    
    recherche = st.text_input("Mot-clé à rechercher :", placeholder="ex: MB-2026-001, Aspirine, 2026-02...")
    
    if st.button("Chercher", type="primary", key="btn_search"):
        if recherche:
            with st.spinner("Recherche dans les archives Google Drive..."):
                # On cherche uniquement des dossiers (mimeType folder) contenant le mot-clé
                query = f"name contains '{recherche}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                # orderBy='createdTime desc' permet d'avoir les plus récents en premier
                results = service.files().list(q=query, spaces='drive', orderBy='createdTime desc', fields='files(id, name, webViewLink)').execute()
                dossiers = results.get('files', [])
                
                if dossiers:
                    st.success(f"✅ {len(dossiers)} dossier(s) trouvé(s) :")
                    for d in dossiers:
                        # Crée un lien cliquable qui ouvre le dossier Drive dans un nouvel onglet
                        st.markdown(f"📂 **[{d['name']}]({d['webViewLink']})**")
                else:
                    st.info("Aucun dossier trouvé avec ce mot-clé.")
        else:
            st.warning("Veuillez entrer un mot-clé.")


# ---------------------------------------------------------
# ONGLET 1 : FORMULAIRE DE NOUVELLE MANIP
# ---------------------------------------------------------
with tab_nouvelle:
    now = datetime.now()
    annee = now.strftime("%Y")
    mois = now.strftime("%m")
    date_str = now.strftime("%Y-%m-%d")
    heure_str = now.strftime("%H:%M")

    titre = st.text_input("Titre de la manip*", placeholder="ex: Synthèse de l'Aspirine")

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        code_manip = st.text_input("🔢 Code de la manip", placeholder="ex: MB-2026-001")
    with col_meta2:
        noms_donnees = st.text_input("📊 Noms des données associées", placeholder="ex: RMN_lot2, spectres_IR.zip...")

    col1, col2 = st.columns(2)
    with col1:
        choix_app = st.selectbox("🔬 Appareil", [""] + historique["appareils"] + ["➕ Nouveau..."])
        appareil = st.text_input("Saisir le nouvel appareil :", key="new_app") if choix_app == "➕ Nouveau..." else choix_app
    with col2:
        choix_calib = st.selectbox("⚖️ Calibration", [""] + historique["calibrations"] + ["➕ Nouveau..."])
        calibration = st.text_input("Saisir la nouvelle calibration :", key="new_calib") if choix_calib == "➕ Nouveau..." else choix_calib

    st.markdown("### 🧪 Réactifs")
    if "lignes_reactifs" not in st.session_state: 
        st.session_state.lignes_reactifs = 1
    reactifs_data = []

    cols_header = st.columns([3, 2, 2, 3])
    cols_header[0].markdown("**Nom**")
    cols_header[1].markdown("**Concentration**")
    cols_header[2].markdown("**Solvant**")
    cols_header[3].markdown("**Notes**")

    for i in range(st.session_state.lignes_reactifs):
        cols = st.columns([3, 2, 2, 3])
        with cols[0]:
            choix_r = st.selectbox(f"R{i}", [""] + historique["reactifs"] + ["➕ Nouveau..."], key=f"sel_{i}", label_visibility="collapsed")
            nom_r = st.text_input(f"New R{i}", key=f"new_{i}", placeholder="Nouveau...") if choix_r == "➕ Nouveau..." else choix_r
        with cols[1]: 
            conc_r = st.text_input(f"C{i}", key=f"conc_{i}", label_visibility="collapsed", placeholder="Conc")
        with cols[2]: 
            solv_r = st.text_input(f"S{i}", key=f"solv_{i}", label_visibility="collapsed", placeholder="Solvant")
        with cols[3]: 
            notes_r = st.text_input(f"N{i}", key=f"notes_{i}", label_visibility="collapsed", placeholder="Notes")
        
        if nom_r: 
            reactifs_data.append({"nom": nom_r, "conc": conc_r, "solv": solv_r, "notes": notes_r})

    if st.button("➕ Ajouter un réactif"): 
        st.session_state.lignes_reactifs += 1
        st.rerun()

    description = st.text_area("📝 Descriptif de la manip", height=150)
    fichiers = st.file_uploader("📎 Pièces jointes (Photos, PDF...)", accept_multiple_files=True)

    if fichiers:
        st.markdown("### 👀 Aperçu avant sauvegarde")
        onglets = st.tabs([f.name for f in fichiers])
        
        for i, fichier in enumerate(fichiers):
            with onglets[i]:
                nom_f = fichier.name.lower()
                if nom_f.endswith(('.png', '.jpg', '.jpeg')):
                    st.image(fichier, use_container_width=True)
                elif nom_f.endswith('.pdf'):
                    base64_pdf = base64.b64encode(fichier.getvalue()).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                else:
                    st.info("Aperçu non disponible pour ce type de fichier.")

    st.markdown("---")

    if st.button("💾 Enregistrer la manip", type="primary"):
        if not titre:
            st.error("⚠️ Il te faut au moins un titre pour enregistrer la manip !")
        else:
            with st.spinner("Création des dossiers et envoi vers Google Drive..."):
                
                if appareil and appareil not in historique["appareils"]: historique["appareils"].append(appareil.strip())
                if calibration and calibration not in historique["calibrations"]: historique["calibrations"].append(calibration.strip())
                for r in reactifs_data:
                    if r["nom"] and r["nom"] not in historique["reactifs"]: historique["reactifs"].append(r["nom"].strip())
                
                st.session_state.historique = historique
                
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_hist:
                    json.dump(historique, tmp_hist, ensure_ascii=False)
                    tmp_hist_path = tmp_hist.name
                upload_file(tmp_hist_path, NOM_FICHIER_HISTO, DOSSIER_RACINE_ID, 'application/json')

                id_annee = get_or_create_folder(annee, DOSSIER_RACINE_ID)
                id_mois = get_or_create_folder(mois, id_annee)
                
                # --- NOUVELLE RÈGLE DE NOMMAGE ---
                # On prend le code_manip s'il existe, SINON on prend le titre.
                nom_base = code_manip if code_manip else titre
                # Le dossier commence obligatoirement par Date_Heure_ suivi du Code (ou du Titre)
                nom_dossier = f"{date_str}_{heure_str.replace(':', 'h')}_{nom_base.replace(' ', '_').replace('/', '-')}"
                
                id_manip = get_or_create_folder(nom_dossier, id_mois)

                fichiers_html = ""
                with tempfile.TemporaryDirectory() as temp_dir:
                    for fichier in fichiers:
                        chemin_temp = os.path.join(temp_dir, fichier.name)
                        with open(chemin_temp, "wb") as f:
                            f.write(fichier.getbuffer())
                        
                        upload_file(chemin_temp, fichier.name, id_manip)
                        
                        nom_f = fichier.name.lower()
                        if nom_f.endswith(('.png', '.jpg', '.jpeg')):
                            fichiers_html += f"<h3>📷 Image : {fichier.name}</h3><img src='{fichier.name}' style='max-width:100%; border:1px solid var(--border-color); border-radius: 5px;'><br><br>"
                        elif nom_f.endswith('.pdf') and HAS_FITZ:
                            doc = fitz.open(chemin_temp)
                            fichiers_html += f"<h3>📄 Note (PDF) : {fichier.name}</h3>"
                            for num_page in range(len(doc)):
                                page = doc.load_page(num_page)
                                pix = page.get_pixmap(dpi=150)
                                nom_img_pdf = f"{fichier.name}_page_{num_page + 1}.png"
                                chemin_img_pdf = os.path.join(temp_dir, nom_img_pdf)
                                pix.save(chemin_img_pdf)
                                upload_file(chemin_img_pdf, nom_img_pdf, id_manip, 'image/png')
                                fichiers_html += f"<p><em>Page {num_page + 1}</em></p><img src='{nom_img_pdf}' style='max-width:100%; border:1px solid var(--border-color); border-radius: 5px; margin-bottom: 20px;'><br>"
                            doc.close()
                        else:
                            fichiers_html += f"<h3>📄 Fichier joint : {fichier.name}</h3><embed src='{fichier.name}' width='100%' height='800px'><br><br>"

                    reactifs_html = ""
                    if reactifs_data:
                        reactifs_html = """
                        <h2>🧪 Réactifs utilisés</h2>
                        <table>
                            <thead>
                                <tr><th>Nom du réactif</th><th>Concentration</th><th>Solvant</th><th>Notes</th></tr>
                            </thead>
                            <tbody>
                        """
                        for r in reactifs_data: 
                            reactifs_html += f"<tr><td><strong>{r['nom']}</strong></td><td>{r['conc']}</td><td>{r['solv']}</td><td>{r['notes']}</td></tr>"
                        reactifs_html += "</tbody></table>"

                    html_content = f"""
                    <!DOCTYPE html>
                    <html lang="fr">
                    <head>
                        <meta charset="UTF-8">
                        <title>{date_str} - {titre}</title>
                        <style>
                            :root {{ --bg-color: #ffffff; --text-color: #333333; --h1-color: #2c3e50; --border-color: #3498db; --desc-bg: #f9f9f9; --btn-bg: #eeeeee; --table-border: #dddddd; --table-head: #f2f2f2; }}
                            [data-theme="dark"] {{ --bg-color: #1e1e1e; --text-color: #f0f0f0; --h1-color: #5faee3; --border-color: #5faee3; --desc-bg: #2d2d2d; --btn-bg: #444444; --table-border: #444444; --table-head: #2d2d2d; }}
                            
                            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 900px; line-height: 1.6; background-color: var(--bg-color); color: var(--text-color); position: relative; }}
                            h1, h2, h3 {{ color: var(--h1-color); border-bottom: 2px solid var(--border-color); padding-bottom: 5px; }}
                            .description {{ background: var(--desc-bg); padding: 20px; border-left: 5px solid var(--border-color); margin-bottom: 20px; white-space: pre-wrap; }}
                            .meta-box {{ background: var(--desc-bg); padding: 15px; border-radius: 8px; margin-bottom: 20px; display: inline-block; min-width: 50%; }}
                            .meta-box p {{ margin: 5px 0; }}
                            
                            table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
                            th, td {{ border: 1px solid var(--table-border); padding: 12px; text-align: left; }}
                            th {{ background-color: var(--table-head); font-weight: bold; }}
                            
                            #theme-toggle {{ position: absolute; top: 0; right: 0; padding: 8px 12px; cursor: pointer; background: var(--btn-bg); color: var(--text-color); border: 1px solid var(--border-color); border-radius: 5px; font-weight: bold; }}
                            @media print {{ body {{ background: white !important; color: black !important; }} #theme-toggle {{ display: none; }} img, embed {{ page-break-inside: avoid; }} }}
                        </style>
                    </head>
                    <body>
                        <button id="theme-toggle" onclick="toggleTheme()">🌓 Thème</button>

                        <h1>🧪 {titre}</h1>
                        
                        <div class="meta-box">
                            <p><strong>📅 Date :</strong> {date_str} à {heure_str}</p>
                            {f"<p><strong>🔢 Code manip :</strong> {code_manip}</p>" if code_manip else ""}
                            {f"<p><strong>📊 Données associées :</strong> {noms_donnees}</p>" if noms_donnees else ""}
                            {f"<p><strong>🔬 Appareil :</strong> {appareil}</p>" if appareil else ""}
                            {f"<p><strong>⚖️ Calibration :</strong> {calibration}</p>" if calibration else ""}
                        </div>
                        
                        {reactifs_html}
                        
                        <h2>📝 Descriptif écrit</h2>
                        <div class="description">{description if description else "Aucune description encodée."}</div>
                        
                        <h2>📎 Fichiers attachés</h2>
                        {fichiers_html if fichiers_html else "<p>Aucun fichier n'a été uploadé.</p>"}

                        <script>
                            function toggleTheme() {{
                                const root = document.documentElement;
                                root.getAttribute('data-theme') === 'dark' ? root.removeAttribute('data-theme') : root.setAttribute('data-theme', 'dark');
                            }}
                            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {{ document.documentElement.setAttribute('data-theme', 'dark'); }}
                        </script>
                    </body>
                </html>
                """
                chemin_html = os.path.join(temp_dir, "rapport.html")
                with open(chemin_html, "w", encoding="utf-8") as f: 
                    f.write(html_content)
                upload_file(chemin_html, "rapport.html", id_manip, 'text/html')

            st.success("✅ Manip envoyée avec succès sur Google Drive ! 🎉")
            st.session_state.lignes_reactifs = 1
