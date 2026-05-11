import streamlit as st
import pandas as pd
import plotly.express as px
import re
import os

# Configuration de la page pour utiliser toute la largeur de l'écran
st.set_page_config(page_title="Dashboard Aviron", layout="wide")

# --- FONCTIONS DE PRÉPARATION ---
@st.cache_data
def load_data():
    df = pd.read_csv('base_donnees_aviron_full_clean.csv', sep=';')
    
    # On récupère la date de modification du fichier
    # Si le fichier change sur GitHub, cette date changera et Streamlit videra le cache tout seul !
    file_path = 'base_donnees_aviron_full_clean.csv'
    file_stats = os.stat(file_path)
    
    df = pd.read_csv(file_path, sep=';')

    def time_to_seconds(t):
        if pd.isna(t) or type(t) != str or ':' not in t: return None
        try:
            m, s = t.split(':')
            return int(m) * 60 + float(s)
        except:
            return None
            
    df['Temps_sec'] = df['Temps'].apply(time_to_seconds)
    df['Type_Finale'] = df['Type_Finale'].fillna('Inconnu')
    
    # --- LOGIQUE DE CATÉGORISATION (DISCIPLINE) ---
    def categoriser_championnat(nom):
        if pd.isna(nom): return "Rivière"
        nom_upper = str(nom).upper()
        
        if 'MER' in nom_upper.split() or 'BRS' in nom_upper or 'BEACH' in nom_upper:
            return 'Mer'
        elif 'LONGUE DISTANCE' in nom_upper:
            return 'Longue Distance'
        elif re.search(r'\bPR\b', nom_upper) or 'PARA' in nom_upper:
            return 'PR'
        elif 'UNSS' in nom_upper or 'FFSU' in nom_upper:
            return 'UNSS'
        else:
            return 'Rivière'
            
    df['Discipline'] = df['Championnat'].apply(categoriser_championnat)
    
    # --- NOUVELLE LOGIQUE D'AFFICHAGE DES CLUBS (Noms propres) ---
    # On identifie dynamiquement toutes les colonnes Club_1, Club_2, etc.
    # --- NOUVELLE LOGIQUE D'AFFICHAGE DES CLUBS (Noms propres) ---
    # On identifie dynamiquement toutes les colonnes Club_1, Club_2, etc.
    colonnes_clubs = [col for col in df.columns if re.match(r'^Club_\d+$', col)]
    
    if len(colonnes_clubs) > 0:
        def fusionner_clubs_propres(row):
            # On récupère tous les noms nettoyés qui ne sont pas vides
            clubs_presents = [str(row[c]) for c in colonnes_clubs if pd.notna(row[c]) and str(row[c]).strip() != ""]
            return " / ".join(clubs_presents) if clubs_presents else "INCONNU"
            
        # On écrase l'ancienne colonne Club "sale" par notre belle concaténation de clubs propres
        df['Club'] = df.apply(fusionner_clubs_propres, axis=1)
    
    return df

def seconds_to_time(s):
    if pd.isna(s): return ""
    m = int(s // 60)
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"

df = load_data()

# --- RECHERCHE RAMEUR (GLOBALE) ---
st.title("🚣‍♂️ Tableau de Bord - Résultats d'Aviron")

colonnes_rameurs = [col for col in df.columns if 'Rameur' in col or 'Barreur' in col]
tous_les_rameurs = pd.concat([df[col] for col in colonnes_rameurs]).dropna().unique()
tous_les_rameurs = sorted(tous_les_rameurs)

recherche_rameur = st.multiselect(
    "🔍 Rechercher un ou plusieurs rameurs (Cherche sur TOUTES les disciplines) :", 
    options=tous_les_rameurs,
    placeholder="Commencez à taper..."
)

if recherche_rameur:
    st.markdown(f"### 📋 Historique des courses pour : {', '.join(recherche_rameur)}")
    
    mask = df[colonnes_rameurs].isin(recherche_rameur).any(axis=1)
    colonnes_historique = ['Année', 'Discipline', 'Championnat', 'Code_Course', 'Type_Finale', 'Position', 'Temps', 'Club'] + colonnes_rameurs
    
    df_historique_trie = df[mask][colonnes_historique].sort_values(
        by=['Année', 'Code_Course', 'Type_Finale', 'Position'], 
        ascending=[True, True, True, True]
    )
    
    st.dataframe(df_historique_trie, use_container_width=True, hide_index=True)

st.divider()

# --- SÉLECTION DE LA DISCIPLINE ---
st.markdown("### 🌊 Choisissez une discipline")
discipline_choisie = st.radio(
    "Discipline",
    options=["Rivière", "Mer", "Longue Distance", "PR", "UNSS"],
    horizontal=True,
    label_visibility="collapsed"
)

df_discipline = df[df['Discipline'] == discipline_choisie]

# --- FILTRES DE LA COMPÉTITION (Pleine largeur) ---
st.markdown(f"### 🎛️ Filtres ({discipline_choisie})")
c1, c2, c3, c4, c5 = st.columns(5)

# 1. Filtre Année
annees_dispos = sorted(df_discipline['Année'].dropna().unique(), reverse=True)
with c1: 
    filter_annee = st.multiselect("Année", annees_dispos)

df_cascade = df_discipline[df_discipline['Année'].isin(filter_annee)] if filter_annee else df_discipline

# 2. Filtre Championnat
champs_dispos = sorted(df_cascade['Championnat'].dropna().unique())
with c2: 
    filter_champ = st.multiselect("Championnat", champs_dispos)
    
if filter_champ: 
    df_cascade = df_cascade[df_cascade['Championnat'].isin(filter_champ)]

# 3. Filtre CLUB 
colonnes_clubs = [col for col in df.columns if re.match(r'^Club_\d+$', col)]

# SÉCURITÉ : Si aucune colonne Club_1 n'existe, on se base sur la colonne 'Club' classique
if not colonnes_clubs:
    colonnes_clubs = ['Club']

# SÉCURITÉ 2 : On vérifie que le dataframe n'est pas déjà vide à cause du filtre "Année" ou "Championnat"
if not df_cascade.empty:
    clubs_dispos = pd.concat([df_cascade[col] for col in colonnes_clubs]).dropna().unique()
    clubs_dispos = sorted([c for c in clubs_dispos if str(c).strip() != ""])
else:
    clubs_dispos = []

with c3:
    filter_club = st.multiselect("Club", clubs_dispos)
    
if filter_club:
    mask_club = df_cascade[colonnes_clubs].isin(filter_club).any(axis=1)
    df_cascade = df_cascade[mask_club]

# 4. Filtre Catégorie
cats_dispos = sorted(df_cascade['Code_Course'].dropna().unique())
with c4: 
    filter_cat = st.multiselect("Catégorie", cats_dispos)

if filter_cat: 
    df_cascade = df_cascade[df_cascade['Code_Course'].isin(filter_cat)]

# 5. Filtre Finale
finales_dispos = sorted(df_cascade['Type_Finale'].dropna().unique())
with c5: 
    filter_finale = st.multiselect("Finale", finales_dispos)

df_filtre = df_cascade
if filter_finale: 
    df_filtre = df_filtre[df_filtre['Type_Finale'].isin(filter_finale)]

st.divider()

# --- TOP CLUBS (Le vrai Podium Visuel) ---
st.markdown("### 🏆 Podium des Meilleurs Clubs (sur la sélection)")
st.caption("Si un bateau est une entente, chaque club qui le compose marque 1 podium individuellement. (Basé uniquement sur les Finales A)")

# CORRECTION : On filtre pour ne garder que les positions 1 à 3 ET les Finales A 
# (On inclut 'F' et 'FINALE' au cas où ce soit une course à finale unique)
top_equipes = df_filtre[(df_filtre['Type_Finale'].isin(['FA', 'F', 'FINALE'])) & (df_filtre['Position'] <= 3)]

if not top_equipes.empty:
    
    # SÉCURITÉ : Si on a les colonnes Club_1, Club_2, on sépare. Sinon on utilise la colonne Club unique.
    colonnes_pour_podium = [col for col in df.columns if re.match(r'^Club_\d+$', col)]
    if not colonnes_pour_podium:
        colonnes_pour_podium = ['Club']
        
    df_melt = top_equipes.melt(id_vars=['Position'], value_vars=colonnes_pour_podium, value_name='Nom_Club')
    df_melt = df_melt[df_melt['Nom_Club'].notna() & (df_melt['Nom_Club'] != "")]
    
    stats_clubs = df_melt.groupby('Nom_Club').agg(
        Podiums=('Position', 'count'),
        Position_Moyenne=('Position', 'mean')
    ).reset_index()
    
    # Tri : Plus grand nombre de podiums, puis meilleure moyenne
    stats_clubs = stats_clubs.sort_values(by=['Podiums', 'Position_Moyenne'], ascending=[False, True]).head(3)
    clubs_list = stats_clubs.to_dict('records')

    # Fonction pour dessiner les cartes du podium
    def afficher_medaille(club_data, couleur_fond, emoji, marge_haut):
        st.markdown(f"""
        <div style="margin-top: {marge_haut}px; background-color: {couleur_fond}; padding: 15px; border-radius: 10px; text-align: center; color: black; box-shadow: 0px 4px 6px rgba(0,0,0,0.1);">
            <h1 style="margin: 0; font-size: 2.5rem; color: black;">{emoji}</h1>
            <h3 style="margin: 10px 0; font-size: 1.2rem; color: black; word-wrap: break-word;">{club_data['Nom_Club']}</h3>
            <p style="margin: 0; font-size: 1.1rem; color: black;"><b>{club_data['Podiums']}</b> podiums</p>
            <p style="margin: 0; font-size: 0.9rem; color: rgba(0,0,0,0.7);">(Pos moy: {club_data['Position_Moyenne']:.1f})</p>
        </div>
        """, unsafe_allow_html=True)

    # Disposition du podium : Argent (gauche), Or (centre), Bronze (droite)
    col_argent, col_or, col_bronze = st.columns(3)
    
    if len(clubs_list) > 0:
        with col_or:
            afficher_medaille(clubs_list[0], "#FFD700", "🥇", 0) # Pas de marge = plus haut
    if len(clubs_list) > 1:
        with col_argent:
            afficher_medaille(clubs_list[1], "#E8E8E8", "🥈", 0) # Un peu plus bas
    if len(clubs_list) > 2:
        with col_bronze:
            afficher_medaille(clubs_list[2], "#CD7F32", "🥉", 0) # Le plus bas
else:
    st.info("Aucun podium trouvé avec ces filtres.")

st.divider()

# --- MILIEU : LISTE DES COURSES ---
st.markdown("### 📊 Liste des résultats")
st.caption("👆 **Astuce : Cliquez sur la marge à gauche d'une ligne du tableau pour révéler la composition de l'équipage !**")

colonnes_a_afficher = ['Année','Bassin', 'Club', 'Code_Course', 'Type_Finale', 'Position', 'Temps']

df_trié = df_filtre.sort_values(
    by=['Année', 'Code_Course', 'Type_Finale', 'Position'], 
    ascending=[True, True, True, True]
)

event = st.dataframe(
    df_trié[colonnes_a_afficher], 
    use_container_width=True, 
    hide_index=True,
    on_select="rerun", 
    selection_mode="single-row"
)

# --- AFFICHAGE DE L'ÉQUIPAGE AU CLIC ---
if event and len(event.selection.rows) > 0:
    index_clique = event.selection.rows[0]
    ligne_selectionnee = df_trié.iloc[index_clique]
    
    st.info(f"🚣‍♂️ **Équipage : {ligne_selectionnee['Club']}** — {ligne_selectionnee['Code_Course']} (Finale {ligne_selectionnee['Type_Finale']})")
    
    equipiers = []
    
    for col in colonnes_rameurs:
        nom = ligne_selectionnee[col]
        if pd.notna(nom) and str(nom).strip() != "":
            titre_propre = col.replace('_', ' ')
            equipiers.append(f"**{titre_propre}** : {nom}")
            
    if len(equipiers) > 0:
        colonnes_affichage = st.columns(min(len(equipiers), 4))
        for i, equipier in enumerate(equipiers):
            colonnes_affichage[i % 4].markdown(equipier)
    else:
        st.warning("Aucun équipage n'a été renseigné pour ce bateau dans la base de données.")

st.divider()

# --- BAS : GRAPHIQUES ET PRONO ---
if len(filter_cat) == 1:
    cat_selectionnee = filter_cat[0]
    st.markdown(f"### 📈 Analyse approfondie pour la catégorie : {cat_selectionnee}")
    
    col_gauche, col_milieu, col_droite = st.columns(3)
    
    # 1. On filtre sur la discipline et la catégorie (Code)
    df_cat = df_discipline[df_discipline['Code_Course'] == cat_selectionnee]
    
    # 2. NOUVEAU : On applique le filtre Championnat s'il a été sélectionné plus haut !
    if 'filter_champ' in locals() and filter_champ:
        df_cat = df_cat[df_cat['Championnat'].isin(filter_champ)]

    # --- En bas à gauche : Podiums ---
    with col_gauche:
        st.markdown("**Temps moyen des Podiums (FA, Pos 1 à 3)**")
        podiums = df_cat[(df_cat['Type_Finale'] == 'FA') & (df_cat['Position'] <= 3)]
        if not podiums.empty:
            # On trie bien par année pour éviter le zigzag
            evo_podium = podiums.groupby('Année')['Temps_sec'].mean().reset_index().sort_values('Année')
            evo_podium['Temps_Affiche'] = pd.to_datetime(evo_podium['Temps_sec'], unit='s')
            
            fig1 = px.line(evo_podium, x='Année', y='Temps_Affiche', markers=True)
            # autorange="reversed" met les temps rapides en haut !
            fig1.update_yaxes(tickformat="%M:%S", title_text="Temps (Min:Sec)", autorange="reversed")
            fig1.update_traces(hovertemplate="<b>Année:</b> %{x}<br><b>Temps:</b> %{y|%M:%S}<extra></extra>")
            
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.warning("Pas assez de données de podiums.")

    # --- En bas au milieu : Évolution par finale ---
    with col_milieu:
        st.markdown("**Temps moyen par type de finale**")
        finales_cibles = ['FA', 'FB', 'FC', 'FD']
        df_finales = df_cat[df_cat['Type_Finale'].isin(finales_cibles)]
        
        if not df_finales.empty:
            evo_finales = df_finales.groupby(['Année', 'Type_Finale'])['Temps_sec'].mean().reset_index()
            evo_finales['Temps_Affiche'] = pd.to_datetime(evo_finales['Temps_sec'], unit='s')
            
            evo_finales['Type_Finale'] = pd.Categorical(evo_finales['Type_Finale'], categories=finales_cibles, ordered=True)
            # Le double tri (Finale PUIS Année) répare la courbe en pelote de laine
            evo_finales = evo_finales.sort_values(['Type_Finale', 'Année'])
            
            fig2 = px.line(evo_finales, x='Année', y='Temps_Affiche', color='Type_Finale', markers=True)
            fig2.update_yaxes(tickformat="%M:%S", title_text="Temps (Min:Sec)", autorange="reversed")
            fig2.update_traces(hovertemplate="<b>Finale:</b> %{data.name}<br><b>Année:</b> %{x}<br><b>Temps:</b> %{y|%M:%S}<extra></extra>")
            
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Pas assez de données pour les finales.")

    # --- En bas à droite : Liste Année/Temps et PRONO ---
    with col_droite:
        st.markdown("**Meilleurs temps (1ers de FA) par année**")
        premiers_fa = df_cat[(df_cat['Type_Finale'] == 'FA') & (df_cat['Position'] == 1)]
        
        if not premiers_fa.empty:
            lignes_propres = []
            for annee, group in premiers_fa.groupby('Année'):
                if len(group) > 1:
                    # On cherche un slash "/" tout court (avec ou sans espaces)
                    group_sans_mix = group[~group['Club'].str.contains('/', na=False)]
                    
                    if not group_sans_mix.empty:
                        # Il y a au moins un club unique ! On le garde
                        meilleur = group_sans_mix.sort_values('Temps_sec').head(1)
                        lignes_propres.append(meilleur)
                    else:
                        # Il n'y a QUE des mixtes pour cette position 1 (ex: certains 2-). On garde le meilleur.
                        meilleur = group.sort_values('Temps_sec').head(1)
                        lignes_propres.append(meilleur)
                else:
                    lignes_propres.append(group)
                    
            premiers_fa_filtres = pd.concat(lignes_propres)
            
            liste_temps = premiers_fa_filtres[['Année', 'Club', 'Temps']].sort_values(by='Année', ascending=False)
            st.dataframe(liste_temps, hide_index=True, use_container_width=True)
            
            # CORRECTION PRONO : On isole les données à partir de 2019 (inclus)
            # On s'assure que l'année est bien considérée comme un nombre
            premiers_fa_filtres['Année_Num'] = pd.to_numeric(premiers_fa_filtres['Année'], errors='coerce')
            premiers_recents = premiers_fa_filtres[premiers_fa_filtres['Année_Num'] >= 2019]
            
            # Sécurité : Si jamais une catégorie n'a plus été courue depuis 2018, 
            # on se rabat sur la moyenne globale pour éviter un crash
            if not premiers_recents.empty:
                moyenne_historique_sec = premiers_recents['Temps_sec'].mean()
                texte_prono = "depuis 2019"
            else:
                moyenne_historique_sec = premiers_fa_filtres['Temps_sec'].mean()
                texte_prono = "sur tout l'historique (pas de course depuis 2019)"
                
            temps_prono = seconds_to_time(moyenne_historique_sec)
            
            st.error(f"### 🎯 PRONO TEMPS GAGNANT : {temps_prono}")
            st.caption(f"(Moyenne des premiers de la finale A {texte_prono})")
        else:
            st.warning("Aucun premier de FA trouvé.")

# --- PIED DE PAGE / COPYRIGHT ---
st.divider() # Ajoute une belle ligne de séparation

st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em; padding-bottom: 20px;'>
        © 2026 Dashboard Aviron. Tous droits réservés.<br>
        <i>Développé par <a href="https://www.linkedin.com/in/pierre-bourgeois-655464234" target="_blank" style="color: gray;">Pierre BOURGEOIS</a></i>
    </div>
    """, 
    unsafe_allow_html=True
)