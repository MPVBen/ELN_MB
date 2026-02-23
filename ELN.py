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

# --- ☁️ 2. CONNEXION À GOOGLE DRIVE (Version Humain / OAuth) ---
@st.cache_resource
def get_drive_service():
    creds_info = json.loads(st.secrets["TOKEN_GCP"])
    creds = Credentials.from_authorized_user_info(
        creds_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

service = get_drive_service()
DOSSIER_RACINE_ID = st.secrets["DOSSIER_RACINE_ID"]

# Fonctions utilitaires pour Google Drive
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

# --- 🧠 3. GESTION DE L'HISTORIQUE SUR LE DRIVE ---
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

# CHARGEMENT OPTIMISÉ (Anti-Timeout)
if "historique" not in st.session_state:
    with st.spinner("Connexion au Drive et chargement de la mémoire..."):
        try:
            st.session_state.historique = charger_historique_drive()
        except Exception as e:
            st.warning("⚠️ Délai d'attente dépassé pour le Drive, utilisation d'un historique vide pour l'instant.")
            st.session_state.historique = {"appareils": [], "calibrations": [], "reactifs": []}

historique = st.session_state.historique

# --- 🧪 4. INTERFACE UTILISATEUR PRINCIPALE ---
st.title("🧪 Nouvelle Entrée Labo")

now = datetime.now()
annee = now.strftime("%Y")
mois = now.strftime("%m")
date_str = now.strftime("%Y-%m-%d")
heure_str = now.strftime("%H:%M")

titre = st.text_input("Titre de la manip*", placeholder="ex: Synthèse de l'Aspirine")

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

# --- 💾 5. SAUVEGARDE VERS GOOGLE DRIVE ---
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
            nom_dossier = f"{date_str}_{heure_str.replace(':', 'h')}_{titre.replace(' ', '_').replace('/', '-')}"
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
                        fichiers_html += f"<h3>📷 Image : {fichier.name}</h3><img src='{fichier.name}' style='max-width:100%; border:1px solid #ccc; border-radius: 5px;'><br><br>"
                    elif nom_f.endswith('.pdf') and HAS_FITZ:
                        # Découpage du PDF pour un bel affichage
                        doc = fitz.open(chemin_temp)
                        fichiers_html += f"<h3>📄 Note (PDF) : {fichier.name}</h3>"
                        for num_page in range(len(doc)):
                            page = doc.load_page(num_page)
                            pix = page.get_pixmap(dpi=150)
                            nom_img_pdf = f"{fichier.name}_page_{num_page + 1}.png"
                            chemin_img_pdf = os.path.join(temp_dir, nom_img_pdf)
                            pix.save(chemin_img_pdf)
                            upload_file(chemin_img_pdf, nom_img_pdf, id_manip, 'image/png')
                            fichiers_html += f"<img src='{nom_img_pdf}' style='max-width:100%; border:1px solid #ccc; border-radius: 5px; margin-bottom: 20px;'><br>"
                        
                        # Libération du fichier pour éviter l'erreur Windows 32
                        doc.close()
                    else:
                        fichiers_html += f"<h3>📄 Fichier joint : {fichier.name}</h3><embed src='{fichier.name}' width='100%' height='800px'><br><br>"

                reactifs_html = ""
                if reactifs_data:
                    reactifs_html = """
                    <table border='1' style='width:100%; border-collapse: collapse; text-align: left; margin-bottom: 20px;'>
                        <tr style='background-color: #f2f2f2;'><th>Nom du réactif</th><th>Concentration</th><th>Solvant</th><th>Notes</th></tr>
                    """
                    for r in reactifs_data: 
                        reactifs_html += f"<tr><td>{r['nom']}</td><td>{r['conc']}</td><td>{r['solv']}</td><td>{r['notes']}</td></tr>"
                    reactifs_html += "</table>"

                html_content = f"""
                <html lang="fr">
                <head>
                    <meta charset="UTF-8">
                    <title>{titre}</title>
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: auto; padding: 20px; line-height: 1.6; color: #333; }} 
                        img {{ page-break-inside: avoid; }}
                        th, td {{ padding: 10px; border: 1px solid #ddd; }}
                        .meta-box {{ background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #ddd; }}
                    </style>
                </head>
                <body>
                    <h1 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">🧪 {titre}</h1>
                    <div class="meta-box">
                        <p><strong>📅 Date:</strong> {date_str} à {heure_str}</p>
                        {f"<p><strong>🔬 Appareil:</strong> {appareil}</p>" if appareil else ""}
                        {f"<p><strong>⚖️ Calibration:</strong> {calibration}</p>" if calibration else ""}
                    </div>
                    {reactifs_html if reactifs_html else ""}
                    <h2 style="color: #2c3e50;">📝 Descriptif écrit</h2>
                    <div style="background: #f9f9f9; padding: 15px; border-left: 4px solid #3498db; white-space: pre-wrap; margin-bottom: 30px;">{description if description else "Aucune description."}</div>
                    <hr>
                    <h2 style="color: #2c3e50;">📎 Fichiers attachés</h2>
                    {fichiers_html if fichiers_html else "<p>Aucun fichier n'a été uploadé.</p>"}
                </body>
                </html>
                """
                chemin_html = os.path.join(temp_dir, "rapport.html")
                with open(chemin_html, "w", encoding="utf-8") as f: 
                    f.write(html_content)
                upload_file(chemin_html, "rapport.html", id_manip, 'text/html')

        st.success("✅ Manip envoyée avec succès sur Google Drive ! 🎉")
        st.session_state.lignes_reactifs = 1