import pandas as pd
import re
import json
from rapidfuzz import process, fuzz
import os
import datetime

# --- PARAMÈTRES ---
fichier_entree = "base_donnees_aviron.csv"
fichier_sortie = "base_donnees_aviron_enrichie.csv"
fichier_dict_clubs = "dictionnaire_clubs.json"
fichier_dict_noms_ergo = "dictionnaire_noms_ergo.json" 
fichier_ergo = "donnees_ergo.csv" 
fichier_log_ergo = "lissage_noms_ergo_log.txt"

# ==========================================
# 1. CHARGEMENT ET FILTRAGE INCRÉMENTAL STRICT
# ==========================================
print(f"Chargement du fichier brut : {fichier_entree}...")
try:
    # Ajout de low_memory=False pour éviter les DtypeWarnings
    df_brut = pd.read_csv(fichier_entree, sep=';', encoding='utf-8-sig', low_memory=False)
except FileNotFoundError:
    print(f"❌ Erreur : Le fichier {fichier_entree} n'a pas été trouvé.")
    exit()

# Logique Incrémentale : On compare UNIQUEMENT Championnat + Année
if os.path.exists(fichier_sortie):
    # Ajout de low_memory=False ici aussi
    df_existant = pd.read_csv(fichier_sortie, sep=';', encoding='utf-8-sig', low_memory=False)
    
    cles_existantes = set(zip(
        df_existant['Championnat'].astype(str).str.strip(), 
        df_existant['Année'].astype(str).str.strip()
    ))
    
    mask_nouveau = ~df_brut.apply(lambda r: (str(r.get('Championnat', '')).strip(), str(r.get('Année', '')).strip()) in cles_existantes, axis=1)
    df = df_brut[mask_nouveau].copy()
    
    print(f"🔄 Mode Incrémental (Check par Championnat/Année) : {len(df)} nouvelles lignes détectées à enrichir.")
else:
    df_existant = pd.DataFrame()
    df = df_brut.copy()
    print(f"🆕 Création initiale : {len(df)} lignes à traiter.")

if df.empty:
    print("✅ Aucune nouvelle donnée à enrichir depuis la dernière fois. Fin du script !")
    exit()

# ==========================================
# 1.5. FILTRE DES CHRONOS ABERRANTS (< 1min)
# ==========================================
def time_to_seconds_temp(t):
    if pd.isna(t) or type(t) != str or ':' not in t: return None
    try:
        m, s = t.split(':')
        return int(m) * 60 + float(s)
    except: return None

df['Temps_sec_temp'] = df['Temps'].apply(time_to_seconds_temp)
df['Distance_clean'] = df['Distance'].astype(str).str.replace('m', '', case=False).str.strip()

# Condition : Temps < 60s ET Distance n'est pas 250
mask_aberrant = (df['Temps_sec_temp'] < 60) & (df['Distance_clean'] != '250')
nb_aberrants = mask_aberrant.sum()

if nb_aberrants > 0:
    print(f"🧹 Nettoyage de {nb_aberrants} chronos aberrants (< 1 min sur distance ≠ 250m)...")
    df.loc[mask_aberrant, 'Temps'] = None

df = df.drop(columns=['Temps_sec_temp', 'Distance_clean'])

# ==========================================
# 2. CORRECTION DU MOJIBAKE
# ==========================================
print("Correction des accents (Mojibake)...")
encodage_erreurs = {
    'Ã‰': 'É', 'Ã©': 'é', 'Ãˆ': 'È', 'Ã¨': 'è', 'Ã€': 'À', 'Ã ': 'à',
    'Ã‡': 'Ç', 'Ã§': 'ç', 'ÃŽ': 'Î', 'Ã®': 'î', 'Ã”': 'Ô', 'Ã´': 'ô',
    'Ã¯': 'ï', 'Ã‹': 'Ë', 'Ã«': 'ë'
}
for erreur, correction in encodage_erreurs.items():
    df.columns = df.columns.str.replace(erreur, correction, regex=False)

# CORRECTION DU BUG GITHUB ACTIONS : Remplacement de 'str' par 'string'
text_cols = df.select_dtypes(include=['object', 'string']).columns

for col in text_cols:
    for erreur, correction in encodage_erreurs.items():
        df[col] = df[col].str.replace(erreur, correction, regex=False)

# ==========================================
# 3. FONCTIONS DE CLASSIFICATION & LISSAGE
# ==========================================
def determiner_discipline(row):
    championnat = str(row.get('Championnat', '')).upper()
    distance = str(row.get('Distance', '')).strip().lower()
    if "MER" in championnat or "BEACH" in championnat or "BRS" in championnat:
        return "BRS" if distance in ["600", "600.0", "600m"] else "MER"
    elif "INDOOR" in championnat: return "INDOOR"
    elif "FFSU" in championnat or "UNSS" in championnat: return "UNSS/FFSU"
    elif "LONGUE" in championnat: return "LONGUE DISTANCE"
    else: return "RIVIERE"

def lisser_code_course(code):
    if pd.isna(code): return ""
    code = str(code).strip()
    code = re.sub(r'^([HMF])V([A-Z])', r'M\2\1', code)
    code = re.sub(r'^V', 'M', code)
    code = re.sub(r'^FM', 'U15F', code)
    code = re.sub(r'^FS', 'SF', code)
    code = re.sub(r'^HS', 'SH', code)
    remplacements_globaux = {
        "HM": "U15H", "HC": "U17H", "FC": "U17F", "HJ": "U19H", "FJ": "U19F",
        "J14": "U15", "J16": "U17", "J18": "U19", "S-23": "U23", 
        "50%F": "F", "MC4+": "U17M4+", " (BRS)": "", "14-16": "U17", 
        "17-18": "U19", "MS": "SM", "YX": "Yx", " 1H/1F": "","X":"x"
    }
    for vieux, nouveau in remplacements_globaux.items():
        code = code.replace(vieux, nouveau)
    code = re.sub(r'Yx$', 'Yx+', code)
    if re.search(r'(?i)pl', code): code = re.sub(r'(?i)pl', '', code).strip() + " PL"
    mots_a_supprimer_regex = [r'(?i)unss', r'(?i)college', r'(?i)collège', r'(?i)lycee', r'(?i)lycée']
    for mot in mots_a_supprimer_regex: code = re.sub(mot, '', code)
    return code.replace(" Mer", "").replace(" 50%H/F", "").replace("50%H/F", "").strip()

def determiner_categorie(row):
    code = str(row.get('Code_Course', ''))
    code_upper, code_lower = code.upper(), code.lower()
    discipline = str(row.get('Discipline', ''))
    cat = ""
    has_open = "open" in code_lower and discipline != "INDOOR"
    has_pr_kw = any(kw in code_lower for kw in ["pr", "as", "ta", "hst", "ap", "hv"])
    
    if (has_open or has_pr_kw) and "sprint" not in code_lower: cat = "PR"
    elif "U15" in code_upper: cat = "U15"
    elif "U17" in code_upper and "CRIT" in code_upper: cat = "U17 ELITE"
    elif "U17" in code_upper: cat = "U17"
    elif "U19" in code_upper: cat = "U19"
    elif "U23" in code_upper: cat = "U23"
    elif "U" in code_upper and "FFSE" not in code_upper: cat = "UNIVERSITAIRE"
    elif any(kw in code_upper for kw in ["LF", "LG", "LM"]): cat = "LYCEE"
    elif code_upper.startswith(("CF", "CG", "CM", "C4")): cat = "COLLEGE"
    elif code_upper.startswith("M"): cat = "MASTERS"
        
    if not cat:
        if discipline == "INDOOR": cat = code_upper
        else:
            dist_str = str(row.get('Distance', '')).lower().replace('m', '').replace(',', '.').strip()
            try: dist = float(dist_str)
            except: dist = -1
            has_c = "C" in code_upper
            if dist > 2000 or dist == 600: cat = "SENIORS"
            elif dist == 1000: cat = "SPRINTS 1000m"
            elif dist == 2000: cat = "CRITERIUM" if has_c else "SENIORS"
            elif dist == 500: cat = "SPRINTS CRITERIUM" if has_c else "SPRINTS"
    return cat

def determiner_embarcation(row):
    discipline = str(row.get('Discipline', ''))
    categorie = str(row.get('Catégorie', ''))
    code = str(row.get('Code_Course', '')).strip()
    if discipline == "INDOOR": return "ERGO"
    if categorie == "PR": return code
    if not code: return ""
    base = code.split(' ')[0]
    return base + " PL" if " PL" in code else base

print("Calcul des disciplines, codes, catégories et embarcations...")
df['Discipline'] = df.apply(determiner_discipline, axis=1)
df['Code_Course'] = df['Code_Course'].apply(lisser_code_course)
df['Catégorie'] = df.apply(determiner_categorie, axis=1)
df['Embarcation'] = df.apply(determiner_embarcation, axis=1)

# ==========================================
# 4. TRADUCTION ET LISSAGE DES CLUBS
# ==========================================
print("Traduction des codes clubs, lissage manuel et MAJUSCULES...")
dict_clubs = {}
if os.path.exists(fichier_dict_clubs):
    with open(fichier_dict_clubs, "r", encoding="utf-8") as f: dict_clubs = json.load(f)

corrections_clubs_brutes = {
    "Aiguebelette ACL": "Aviron Club du Lac d'Aiguebelette", "Aix les Bains en": "Entente Nautique d'Aix-les-Bains Aviron",
    "Albi AC": "Aviron Club Albigeois", "Angouleme AC": "Aviron Club d'Angouleme", "Annecy CN": "Cercle Nautique d'Annecy",
    "Avignon SN": "Societe Nautique d'Avignon", "Bayonne Av": "Aviron Bayonnais", "Belbeuf CN": "Club Nautique de Belbeuf",
    "Bergerac SN": "Sport Nautique de Bergerac", "Bressoles AC": "Bressols Aviron Club", "Brive CSN": "Club des Sports Nautiques de Brive",
    "Butry sur Oise Voa": "Val d'Oise Aviron", "Caen Calvados SN": "Societe Nautique de Caen et du Calvados",
    "Compiegne SN": "Sport Nautique Compiegnois", "Fenouillet AB": "Aviron du Bocage", "Fontaine Aviron SA": "Association Sportive de Fontaine",
    "Fontainebleau-Avon AN": "Aviron du Pays de Fontainebleau", "Grenoble a": "Aviron Grenoblois", "Lagny SN": "Societe Nautique de Lagny",
    "Le Havre SHA": "Societe Havraise de l'Aviron", "Lorient Scorff": "Aviron du Scorff", "LYON ACLC": "Aviron Club de Lyon-Caluire",
    "Mantes AS": "Association Sportive Mantaise", "Meaux CN": "Cercle Nautique de Meaux", "Melun CN": "Cercle Nautique de Melun",
    "Meulan": "Aviron Meulan-les-Mureaux-Hardricourt", "Mimizan CN": "Cercle Nautique de Mimizan", "Moissac AC": "Aviron Club Moissac",
    "Montargis AC": "Aviron Club Montargis Gatinais", "Montpellier AUC": "Montpellier Aviron Universite Club",
    "Mulhouse Aviron": "Rowing Club de Mulhouse", "Mulhouse RC": "Rowing Club de Mulhouse", "Mulhouse-Aviron": "Rowing Club de Mulhouse",
    "Nancy SN": "Sport Nautique de Nancy", "Nantes LÉO Lagrange": "Club Aviron LEO Lagrange Nantes", "Nice CN": "Club Nautique de Nice",
    "Perreux SN": "Societe Nautique du Perreux", "Pont a Mousson SN": "Societe Nautique de Pont-a-Mousson", "Pont-a-Mousson SN": "Societe Nautique de Pont-a-Mousson",
    "Rouen CNA": "Club Nautique et Athletique de Rouen", "SAINT-MAUR SACSM": "Schelcher Aviron Club de Saint Maur",
    "Saint Cassien Av": "Aviron Saint-Cassien", "Sedan": "Aviron Sedanais", "Sete Av": "Aviron Setois", "Sete ACBT (Santé)": "Aviron Club du Bassin de Thau",
    "SN Oise": "Societe Nautique de l'Oise", "Strasbourg Av": "Aviron Strasbourg 1881", "SUD Gresivaudan CA": "Club d'Aviron du Sud Gresivaudan",
    "Talloires CN": "Cercle Nautique de Talloires", "Thonon CA": "Chablais Aviron Thonon", "Toul US": "Union Sportive de Toul Aviron",
    "Toulouse Av": "Aviron Toulousain", "Valenciennes Aviron": "Valenciennes Universite Club", "Verdun CN": "Cercle Nautique Verdunois",
    "Vichy CAV": "Club de l'Aviron de Vichy", "Villeneuve AV": "Aviron Villeneuvois", "cahors av" : "Aviron Cadurcien",
    "Cercle Nautique Remois": "Cercle Nautique des Regates Remoises", "Reims Reg": "Cercle Nautique des Regates Remoises",
    "Tours Aviron Club": "Aviron Tours Metropole", "Tours ATM": "Aviron Tours Metropole", "Cercle Olympique Tours Sud Aviron": "Aviron Tours Metropole",
    " Association sportive de libourne" : "CLUB NAUTIQUE DE LIBOURNE 1876"
}
corrections_clubs = {k.strip().lower(): v.upper() for k, v in corrections_clubs_brutes.items()}

def formater_club(valeur):
    if pd.isna(valeur) or str(valeur).strip() == "": return ""
    val_str = str(valeur).strip()
    val_lower = val_str.lower()
    if val_str in dict_clubs: return dict_clubs[val_str].upper()
    if val_lower in corrections_clubs: return corrections_clubs[val_lower]
    return val_str.upper()

colonnes_clubs = ["Club1", "Club2", "Club3", "Club4"]
for col in colonnes_clubs: df[col] = df[col].apply(formater_club)

# ==========================================
# 5. NETTOYAGE FUZZY (RAMEURS UNIQUEMENT)
# ==========================================
def lisser_textes_fuzzy(df, colonnes, nom_entite):
    print(f"\n--- Lissage Fuzzy pour : {nom_entite} ---")
    all_items = pd.Series(pd.concat([df[col] for col in colonnes])).dropna()
    all_items = all_items.str.upper().str.strip()
    all_items = all_items[all_items != ""]
    if all_items.empty: return df
    freq = all_items.value_counts()
    key_to_forms = {}
    for item in freq.index:
        key = item.replace(' ', '').replace('-', '')
        if key not in key_to_forms: key_to_forms[key] = []
        key_to_forms[key].append(item)
    key_frequencies = {k: sum(freq[n] for n in forms) for k, forms in key_to_forms.items()}
    sorted_keys = sorted(key_frequencies.keys(), key=lambda k: key_frequencies[k], reverse=True)
    master_keys_mapping = {}
    processed_keys = set()
    for master_key in sorted_keys:
        if master_key in processed_keys: continue
        results = process.extract(master_key, sorted_keys, scorer=fuzz.ratio, limit=10, score_cutoff=95)
        for match_tuple in results:
            match = match_tuple[0]
            if match not in processed_keys:
                master_keys_mapping[match] = master_key
                processed_keys.add(match)
    key_to_best = {}
    for master_key in set(master_keys_mapping.values()):
        all_forms_for_master = []
        for k, mk in master_keys_mapping.items():
            if mk == master_key: all_forms_for_master.extend(key_to_forms[k])
        def score(f): return (f.count(' ') + f.count('-'), freq[f])
        key_to_best[master_key] = sorted(all_forms_for_master, key=score, reverse=True)[0]
    original_to_best = {}
    for item in freq.index:
        key = item.replace(' ', '').replace('-', '')
        master_key = master_keys_mapping[key]
        original_to_best[item] = key_to_best[master_key]
    for col in colonnes:
        df[col] = df[col].str.upper().str.strip().map(original_to_best).fillna(df[col].str.upper().str.strip())
    return df

colonnes_rameurs = [f'Rameur{i}' for i in range(1, 9)] + ['Barreur']
df = lisser_textes_fuzzy(df, colonnes_rameurs, "Rameurs")

# ==========================================
# 6. CORRECTIONS MANUELLES FINALES
# ==========================================
print("\nApplication des ultimes corrections (Lieux, Rameurs, U15)...")
remplacements_rameurs = {'???? ????': 'INCONNU', '421235': 'INCONNU', '????? GULACSY': 'MATHIAS GULACSY'}
for col in colonnes_rameurs: df[col] = df[col].replace(remplacements_rameurs)

corrections_lieux = {'inconnu': 'Mâcon', 'brive la gaillarde': 'Brive-la-Gaillarde', 'gerarmer': 'Gérarmer', 'macon': 'Mâcon', 'mantes la jolie': 'Mantes-la-Jolie', 'thonon': 'Thonon les bains'}
def corriger_lieux(lieu):
    if pd.isna(lieu): return lieu
    lieu_str = str(lieu).strip()
    return corrections_lieux.get(lieu_str.lower(), lieu_str)
df['Lieux'] = df['Lieux'].apply(corriger_lieux)

def corriger_distance_u15(row):
    if row['Catégorie'] == 'U15':
        dist_str = str(row.get('Distance', '')).replace('m', '').replace(',', '.').strip()
        try:
            if float(dist_str) == 2000: return '1000'
        except: pass
    return row['Distance']
df['Distance'] = df.apply(corriger_distance_u15, axis=1)

# ==========================================
# 7. INTÉGRATION ERGO (AVEC CACHE MÉMOIRE)
# ==========================================
print("\n🚀 INTÉGRATION DES PERFORMANCES ERGOMÉTRIQUES (N-1 / N+1) ...")
df['Moyenne_Ergo_Bateau'] = None

if os.path.exists(fichier_ergo):
    df_ergo = pd.read_csv(fichier_ergo, sep=';', encoding='latin-1')
    
    df_ergo['Date test'] = pd.to_datetime(df_ergo['Date test'], format='%d/%m/%Y', errors='coerce')
    def determiner_saison(date_test):
        if pd.isna(date_test): return None
        if date_test.month >= 9: return date_test.year + 1
        else: return date_test.year
    df_ergo['Saison'] = df_ergo['Date test'].apply(determiner_saison)
    
    def ergo_time_to_seconds(t):
        if pd.isna(t) or type(t) != str or ':' not in t: return None
        try:
            m, rest = t.split(':')
            s = rest.replace(',', '.')
            return int(m) * 60 + float(s)
        except: return None
    df_ergo['Temps_sec'] = df_ergo['Temps'].apply(ergo_time_to_seconds)
    
    df_ergo_clean = df_ergo.dropna(subset=['Saison', 'Temps_sec', 'Nom Prénom']).groupby(['Nom Prénom', 'Saison'])['Temps_sec'].min().reset_index()

    dict_noms_ergo = {}
    if os.path.exists(fichier_dict_noms_ergo):
        try:
            with open(fichier_dict_noms_ergo, "r", encoding="utf-8") as f:
                dict_noms_ergo = json.load(f)
        except: pass

    df_complet = pd.concat([df_existant, df], ignore_index=True) if not df_existant.empty else df
    noms_eau = pd.Series(pd.concat([df_complet[col] for col in colonnes_rameurs[:8]])).dropna().str.upper().unique()
    noms_ergo = df_ergo_clean['Nom Prénom'].str.upper().unique()
    
    match_ergo_eau = {}
    logs_ergo = []
    
    nouveaux_noms_ergo = [n for n in noms_ergo if n not in dict_noms_ergo]
    
    print(f"   -> Lissage des noms Ergo ({len(nouveaux_noms_ergo)} nouveaux noms à calculer)...")
    
    for nom_e in noms_ergo:
        if nom_e in dict_noms_ergo:
            match_ergo_eau[nom_e] = dict_noms_ergo[nom_e]
            
    if nouveaux_noms_ergo:
        for nom_e in nouveaux_noms_ergo:
            meilleur_match = process.extractOne(nom_e, noms_eau, scorer=fuzz.token_sort_ratio, score_cutoff=95)
            if meilleur_match:
                nom_officiel = meilleur_match[0]
                dict_noms_ergo[nom_e] = nom_officiel
                match_ergo_eau[nom_e] = nom_officiel
                logs_ergo.append(f"[{meilleur_match[1]}%] ERGO: '{nom_e}'  =>  OFFICIEL: '{nom_officiel}'")
                
        with open(fichier_dict_noms_ergo, "w", encoding="utf-8") as f:
            json.dump(dict_noms_ergo, f, indent=4, ensure_ascii=False)
            
        with open(fichier_log_ergo, "a", encoding="utf-8") as f:
            f.write("\n=== NOUVEAUX AJOUTS ===\n")
            f.write("\n".join(logs_ergo))
        
    df_ergo_clean['Rameur_Officiel'] = df_ergo_clean['Nom Prénom'].str.upper().map(match_ergo_eau)
    df_ergo_clean = df_ergo_clean.dropna(subset=['Rameur_Officiel'])
    
    dict_ergo = df_ergo_clean.set_index(['Rameur_Officiel', 'Saison'])['Temps_sec'].to_dict()
    
    print("   -> Récupération du filet de sécurité (Championnats Indoor 2000m)...")
    
    def time_to_seconds(t):
        if pd.isna(t) or type(t) != str or ':' not in t: return None
        try:
            m, s = t.split(':')
            return int(m) * 60 + float(s)
        except: return None
        
    df_indoor = df_complet[(df_complet['Discipline'] == 'INDOOR') & ((df_complet['Distance'] == '2000') | (df_complet['Distance'] == '2000m'))]
    for _, row in df_indoor.iterrows():
        annee = row['Année']
        temps_sec = time_to_seconds(row['Temps'])
        if temps_sec:
            if pd.notna(row['Rameur1']) and str(row['Rameur1']).strip() != "":
                cle = (str(row['Rameur1']).strip(), annee)
                if cle not in dict_ergo:
                    dict_ergo[cle] = temps_sec

    print("   -> Calcul des moyennes par bateau...")
    
    def calculer_moyenne_ergo_bateau(row):
        cat = str(row.get('Catégorie', '')).upper()
        if 'U15' in cat or 'PR' in cat or 'MASTERS' in cat or 'SPRINT' in cat:
            return None
            
        annee = row['Année']
        temps_rameurs = []
        nb_rameurs_theoriques = 0
        
        for col in colonnes_rameurs[:8]:
            rameur = row[col]
            if pd.notna(rameur) and str(rameur).strip() != "" and str(rameur) != "INCONNU":
                nb_rameurs_theoriques += 1
                t = dict_ergo.get((rameur, annee))
                if t:
                    temps_rameurs.append(t)
                else:
                    t_prev = dict_ergo.get((rameur, annee - 1))
                    t_next = dict_ergo.get((rameur, annee + 1))
                    
                    if t_prev and t_next: temps_rameurs.append((t_prev + t_next) / 2.0)
                    elif t_prev: temps_rameurs.append(t_prev)
                    elif t_next: temps_rameurs.append(t_next)
                        
        if nb_rameurs_theoriques > 0 and len(temps_rameurs) >= (nb_rameurs_theoriques / 2):
            return sum(temps_rameurs) / len(temps_rameurs)
        return None

    df['Moyenne_Ergo_Bateau_sec'] = df.apply(calculer_moyenne_ergo_bateau, axis=1)
    
    def format_ergo(s):
        if pd.isna(s): return ""
        m = int(s // 60)
        sec = s % 60
        return f"{m:02d}:{sec:05.2f}"
        
    df['Moyenne_Ergo_Bateau'] = df['Moyenne_Ergo_Bateau_sec'].apply(format_ergo)
    df = df.drop(columns=['Moyenne_Ergo_Bateau_sec'])
    
else:
    print(f"\nℹ️ Pas de fichier '{fichier_ergo}' trouvé. L'étape d'intégration des ergos est ignorée.")

# ==========================================
# 8. RÉORGANISATION ET SAUVEGARDE FINALE
# ==========================================
ordre_attendu = [
    "Année", "Lieux", "Discipline", "Championnat", "Code_Course", 
    "Catégorie", "Embarcation", "Distance", "Finale", "Position", "Temps", 
    "Moyenne_Ergo_Bateau", 
    "Club1", "Club2", "Club3", "Club4", 
    "Rameur1", "Rameur2", "Rameur3", "Rameur4", "Rameur5", "Rameur6", "Rameur7", "Rameur8", 
    "Barreur"
]

df = df[[c for c in ordre_attendu if c in df.columns]]

if not df_existant.empty:
    df_final = pd.concat([df_existant, df], ignore_index=True)
    df_final = df_final.sort_values(by=["Année", "Championnat", "Code_Course", "Finale", "Position"], ascending=[False, True, True, True, True])
else:
    df_final = df

df_final.to_csv(fichier_sortie, index=False, encoding="utf-8-sig", sep=';')

print(f"\n✅ Fichier enrichi et mis à jour avec succès : {fichier_sortie}")
