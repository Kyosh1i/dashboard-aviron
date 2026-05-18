import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime # N'oublie pas d'ajouter cet import tout en haut de ton fichier avec les autres !
# ==========================================
# CONFIGURATION DE LA SESSION (MULTITHREADING)
# ==========================================
session = requests.Session()
adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
session.mount('https://', adapter)

nom_fichier = "base_donnees_aviron.csv"
fichier_dict_clubs = "dictionnaire_clubs.json"

# ==========================================
# ÉTAPE 0 : VÉRIFICATION DES DONNÉES EXISTANTES
# ==========================================
championnats_deja_faits = set()
df_existant = pd.DataFrame()
dictionnaire_clubs = {}

if os.path.exists(fichier_dict_clubs):
    try:
        with open(fichier_dict_clubs, "r", encoding="utf-8") as f:
            dictionnaire_clubs = json.load(f)
    except Exception as e:
        print(f"⚠️ Erreur lors de la lecture du dictionnaire des clubs : {e}")

if os.path.exists(nom_fichier):
    try:
        df_existant = pd.read_csv(nom_fichier, sep=';', encoding='utf-8-sig')
        if 'Championnat' in df_existant.columns and 'Année' in df_existant.columns:
            couples_existants = df_existant[['Championnat', 'Année']].drop_duplicates()
            for _, ligne in couples_existants.iterrows():
                championnats_deja_faits.add((str(ligne['Championnat']), str(ligne['Année'])))
        print(f"✅ Fichier CSV trouvé ! {len(championnats_deja_faits)} championnats déjà enregistrés.")
    except Exception as e:
        print(f"⚠️ Impossible de lire le fichier CSV existant : {e}")
else:
    print("ℹ️ Aucun fichier CSV existant, on part de zéro.")

def ajouter_club_au_dict(code, nom):
    if code and nom and pd.notna(code) and str(code).strip() != "":
        dictionnaire_clubs[str(code)] = str(nom)

# ==========================================
# FONCTION OUVRIÈRE (EXÉCUTÉE EN PARALLÈLE PAR LES THREADS)
# ==========================================
def traiter_equipage(crew_id, infos_bateau, code_api, annee, rounds, code_course, distance, nom_championnat, lieux):
    temps = infos_bateau.get("adjusted_result")
    if not temps: 
        return None

    position = infos_bateau.get("adjusted_pos")
    round_id = infos_bateau.get("round_id")
    info_round = rounds.get(round_id) or {}
    nom_finale = info_round.get("round_type_code") or info_round.get("shortname") or "Finale"
    
    # Reclassification des finales par paquet de 6
    if nom_finale.upper() in ["FINALE", "F", ""]:
        try:
            pos_int = int(position)
            idx_finale = (pos_int - 1) // 6
            alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if 0 <= idx_finale < len(alphabet):
                nom_finale = f"FA" if idx_finale == 0 else f"F{alphabet[idx_finale]}"
        except:
            pass
            
    est_une_finale_officielle = info_round.get("is_final") is True
    if nom_finale.upper() not in ["FA", "FB", "FC", "FD", "FE", "FF", "FG"] and not est_une_finale_officielle:
        return None

    entry = infos_bateau.get("entry") or {}
    club_dict = entry.get("club") or {}
    
    nouveaux_clubs = [] # On stocke les (code, nom) à ajouter pour le dictionnaire principal
    
    # Requête API de l'équipage
    url_equipage = f"https://api.ffaviron.regatta.time-team.fr/api/1/{code_api}/{annee}/race_crew/{crew_id}"
    try:
        reponse_equipage = session.get(url_equipage, timeout=10)
        data_equipage = reponse_equipage.json() if reponse_equipage.status_code == 200 else {}
    except:
        data_equipage = {}
        
    noms_rameurs = []
    nom_barreur = ""
    stroke_name = entry.get("stroke_fullname")
    codes_clubs_temp = []
    
    entries_data = data_equipage.get("entry") or {}
    for e_id, e_data in entries_data.items():
        e_data_safe = e_data or {}
        rowers = e_data_safe.get("rowers", [])
        coxes = e_data_safe.get("coxes", [])
        
        rowers_safe = [r for r in rowers if r is not None]
        rowers_tries = sorted(rowers_safe, key=lambda x: x.get("position", 99))
        
        for rameur in rowers_tries:
            # 1. On cherche en priorité dans le détail de chaque rameur
            c_mem = rameur.get("club_member") or {}
            c_club = c_mem.get("club") or {}
            c_code = c_club.get("code")
            c_name = c_club.get("name")
            
            if c_code and str(c_code).strip() != "":
                nouveaux_clubs.append((c_code, c_name))
                if c_code not in codes_clubs_temp:
                    codes_clubs_temp.append(c_code)
            elif c_name and str(c_name).strip() != "":
                # Pas de code, on garde le nom !
                if c_name not in codes_clubs_temp:
                    codes_clubs_temp.append(c_name)
            
            fullname = rameur.get("fullname")
            if fullname: noms_rameurs.append(fullname)
                
        for cox in coxes:
            if cox is not None:
                fullname_cox = cox.get("fullname")
                if fullname_cox: nom_barreur = fullname_cox

    # 2. Si les rameurs n'ont rien donné (ou pas de rameurs inscrits), on regarde l'inscription générale
 # 2. Si les rameurs n'ont rien donné (ou pas de rameurs inscrits), on regarde l'inscription générale
    if not codes_clubs_temp:
        c_main_code = club_dict.get("code")
        
        # CORRECTION UNSS : Le nom peut être dans 'club' ou directement à la racine de 'entry'
        c_main_name = club_dict.get("name")
        if not c_main_name:
            c_main_name = entry.get("name")
        
        if c_main_code and str(c_main_code).strip() != "":
            nouveaux_clubs.append((c_main_code, c_main_name))
            codes_clubs_temp.append(c_main_code)
        elif c_main_name and str(c_main_name).strip() != "":
            # Si c'est une entente écrite en brut (ex: "Club A / Club B") sans code global
            if "/" in c_main_name:
                for part in c_main_name.split("/"):
                    p = part.strip()
                    if p and p not in codes_clubs_temp:
                        codes_clubs_temp.append(p)
            else:
                codes_clubs_temp.append(c_main_name.strip())

    # --- ORDRE DES RAMEURS ---
    if stroke_name and len(noms_rameurs) > 1:
        if noms_rameurs[-1] == stroke_name:
            noms_rameurs.reverse()
            
    if len(noms_rameurs) == 0 and stroke_name:
        noms_rameurs.append(stroke_name)
        
    # Sécurisation des listes pour l'export (pour que les colonnes soient toujours alignées)
    while len(noms_rameurs) < 8: noms_rameurs.append("")
    noms_rameurs = noms_rameurs[:8]
    
    while len(codes_clubs_temp) < 4: codes_clubs_temp.append("")
    codes_clubs_temp = codes_clubs_temp[:4]
    
    ligne_finale = {
        "Année": annee, "Lieux": lieux, "Championnat": nom_championnat,
        "Code_Course": code_course, "Distance": distance,
        "Finale": nom_finale, "Position": position, "Temps": temps, 
        "Club1": codes_clubs_temp[0], "Club2": codes_clubs_temp[1], "Club3": codes_clubs_temp[2], "Club4": codes_clubs_temp[3], 
        "Rameur1": noms_rameurs[0], "Rameur2": noms_rameurs[1], "Rameur3": noms_rameurs[2], "Rameur4": noms_rameurs[3], 
        "Rameur5": noms_rameurs[4], "Rameur6": noms_rameurs[5], "Rameur7": noms_rameurs[6], "Rameur8": noms_rameurs[7], 
        "Barreur": nom_barreur
    }
    
    return {"ligne": ligne_finale, "nouveaux_clubs": nouveaux_clubs}

# ==========================================
# ÉTAPE 1 : RÉCUPÉRATION DES CHAMPIONNATS
# ==========================================

cibles = []
print("\nRecherche des championnats pour l'année en cours...")

annee_actuelle = datetime.datetime.now().year

# On ne boucle que sur l'année actuelle pour gagner un temps précieux
for annee_recherche in range(annee_actuelle, annee_actuelle - 1, -1):
    url_archive = f"https://ffaviron.regatta.time-team.fr/?year={annee_recherche}"
    reponse_html = session.get(url_archive)
    soup = BeautifulSoup(reponse_html.text, 'html.parser')
    liens = soup.find_all('a', class_='regatta-card-link')

    for lien in liens:
        titre_tag = lien.find('h1')
        if not titre_tag: continue
        nom_championnat = titre_tag.text.strip()
        
        if "Championnat" in nom_championnat and "Zone" not in nom_championnat and "inter" not in nom_championnat and "zone" not in nom_championnat or "Critérium" in nom_championnat:
            href = lien.get('href')
            parts = [p for p in href.strip('/').split('/') if p]
            
            if len(parts) >= 2:
                annee = parts[-1]
                code_api = parts[-2]
                if str(annee) != str(annee_recherche): continue
                
                cible = (nom_championnat, code_api, annee)
                if cible not in cibles: cibles.append(cible)

print(f"{len(cibles)} championnats cibles trouvés pour {annee_actuelle}.")

# ==========================================
# ÉTAPE 2 : RÉCUPÉRATION DES COURSES
# ==========================================
donnees_finales = [] 

for nom_championnat, code_api, annee in cibles:
    if (str(nom_championnat), str(annee)) in championnats_deja_faits:
        print(f"⏩ [SKIP] {nom_championnat} {annee} est déjà dans le CSV.")
        continue

    url_programme = f"https://api.ffaviron.regatta.time-team.fr/api/1/{code_api}/{annee}/event"
    reponse_prog = session.get(url_programme) 
    if reponse_prog.status_code != 200: continue
    
    print(f"\n[BINGO] Traitement de : {nom_championnat} {annee}")
    data_prog = reponse_prog.json()
    
    lieux = "Inconnu"
    regatta_dict = data_prog.get("regatta", {})
    for reg_id, reg_info in regatta_dict.items():
        ville = reg_info.get("city")
        if ville:
            lieux = ville
            break
    
    dictionnaire_courses = data_prog.get("event", {})
    if isinstance(dictionnaire_courses, list):
        if len(dictionnaire_courses) == 0:
            dictionnaire_courses = {}
        else:
            dictionnaire_courses = {course.get("id", str(i)): course for i, course in enumerate(dictionnaire_courses)}

    liste_ids_courses = list(dictionnaire_courses.keys())
    
    for index, event_id in enumerate(liste_ids_courses): 
        infos_course = dictionnaire_courses[event_id]
        code_course = infos_course.get("code", "Inconnu")
        print(f"   [{index + 1}/{len(liste_ids_courses)}] {code_course} ⚡ (Multithreading)")
        
        url_finale = f"https://api.ffaviron.regatta.time-team.fr/api/1/{code_api}/{annee}/event/{event_id}/final"
        reponse_finale = session.get(url_finale)
        
        if reponse_finale.status_code == 200:
            data_finale = reponse_finale.json()
            
            # --- RÉCUPÉRATION DE LA DISTANCE (Anti-Bug Liste) ---
            distance = ""
            races_info = data_finale.get("race", {})
            if isinstance(races_info, dict):
                liste_races = races_info.values()
            elif isinstance(races_info, list):
                liste_races = races_info
            else:
                liste_races = []
                
            for r_info in liste_races:
                if isinstance(r_info, dict):
                    dist = r_info.get("timing_layout", {}).get("distance")
                    if dist:
                        distance = dist
                        break
            
            race_crews = data_finale.get("race_crew") or data_finale.get("round_crew") or {}
            rounds = data_finale.get("round", {}) 
            
            # Lancement des threads (Ouvriers virtuels)
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = []
                for crew_id, infos_bateau in race_crews.items():
                    futures.append(executor.submit(
                        traiter_equipage, crew_id, infos_bateau, code_api, annee, rounds, code_course, distance, nom_championnat, lieux
                    ))
                
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        donnees_finales.append(result["ligne"])
                        for c_code, c_name in result["nouveaux_clubs"]:
                            ajouter_club_au_dict(c_code, c_name)
                            
    # SAUVEGARDE INTERMÉDIAIRE
    if len(donnees_finales) > 0:
        df_nouveaux = pd.DataFrame(donnees_finales)
        df_temp = pd.concat([df_existant, df_nouveaux], ignore_index=True) if not df_existant.empty else df_nouveaux
        try:
            df_temp.to_csv(nom_fichier, index=False, encoding="utf-8-sig", sep=';')
            with open(fichier_dict_clubs, "w", encoding="utf-8") as f:
                json.dump(dictionnaire_clubs, f, indent=4, ensure_ascii=False)
        except PermissionError:
            print(f"\n[ATTENTION] Ferme ton fichier Excel !")

# ==========================================
# EXPORTATION FINALE ET TRI
# ==========================================
print("\n=== COLLECTE TERMINÉE ===")
if len(donnees_finales) > 0:
    df_nouveaux = pd.DataFrame(donnees_finales)
    df_complet = pd.concat([df_existant, df_nouveaux], ignore_index=True) if not df_existant.empty else df_nouveaux
    df_complet = df_complet.sort_values(by=["Année", "Championnat", "Code_Course", "Finale", "Position"])
    
    ordre_colonnes = [
        "Année", "Lieux", "Championnat", "Code_Course", "Distance", 
        "Finale", "Position", "Temps", "Club1", "Club2", "Club3", "Club4", 
        "Rameur1", "Rameur2", "Rameur3", "Rameur4", "Rameur5", "Rameur6", "Rameur7", "Rameur8", "Barreur"
    ]
    df_complet = df_complet[[c for c in ordre_colonnes if c in df_complet.columns]]
    
    try:
        df_complet.to_csv(nom_fichier, index=False, encoding="utf-8-sig", sep=';')
        with open(fichier_dict_clubs, "w", encoding="utf-8") as f:
            json.dump(dictionnaire_clubs, f, indent=4, ensure_ascii=False)
            
        print(f"Fichier global mis à jour avec succès : {nom_fichier}")
    except: pass
else:
    print("Aucun nouveau championnat n'a été ajouté au fichier existant.")