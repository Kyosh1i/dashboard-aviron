import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import re
import unicodedata

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Dashboard Aviron", layout="wide", initial_sidebar_state="expanded")

# Ajout d'un peu d'espace (3rem) en haut pour éviter le chevauchement avec le bandeau Streamlit
st.markdown("""
    <style>
        .block-container {
            padding-top: 3rem; 
            padding-bottom: 1rem;
        }
        h1 {
            margin-top: 0rem !important;
            padding-top: 0rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION DE LA MÉMOIRE (SESSION STATE) ---
if 'custom_ergos' not in st.session_state:
    st.session_state.custom_ergos = {}
if 'boat_selection' not in st.session_state:
    st.session_state.boat_selection = []

# --- FONCTIONS DE PRÉPARATION ---
@st.cache_data
def load_data():
    df = pd.read_csv('base_donnees_aviron_enrichie.csv', sep=';')
    
    def time_to_seconds(t):
        if pd.isna(t) or type(t) != str or ':' not in t: return None
        try:
            m, s = t.split(':')
            return int(m) * 60 + float(s)
        except: return None
            
    df['Temps_sec'] = df['Temps'].apply(time_to_seconds)
    
    if 'Moyenne_Ergo_Bateau' in df.columns:
        df['Moyenne_Ergo_sec'] = df['Moyenne_Ergo_Bateau'].apply(time_to_seconds)
    else:
        df['Moyenne_Ergo_Bateau'] = ""
        df['Moyenne_Ergo_sec'] = None

    df['Finale'] = df['Finale'].fillna('Inconnu')
    
    colonnes_clubs = ['Club1', 'Club2', 'Club3', 'Club4']
    def fusionner_clubs_propres(row):
        clubs_presents = [str(row[c]) for c in colonnes_clubs if pd.notna(row[c]) and str(row[c]).strip() != ""]
        return " / ".join(clubs_presents) if clubs_presents else "INCONNU"
        
    df['Club'] = df.apply(fusionner_clubs_propres, axis=1)
    return df

@st.cache_data
def get_pronos_dict(df_main):
    """Pré-calcule le temps prono (moyenne des 1ers de FA sur les 7 dernières années) pour toutes les embarcations"""
    df_fa = df_main[(df_main['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_main['Position'] == 1)].copy()
    df_fa['Année_Num'] = pd.to_numeric(df_fa['Année'], errors='coerce')
    df_recents = df_fa[df_fa['Année_Num'] >= 2019]
    
    dict_pronos = {}
    for eq in df_main['Embarcation'].dropna().unique():
        eq_upper = str(eq).upper()
        df_eq_recent = df_recents[df_recents['Embarcation'].str.upper() == eq_upper]
        if not df_eq_recent.empty:
            dict_pronos[eq_upper] = df_eq_recent['Temps_sec'].mean()
        else:
            df_eq_all = df_fa[df_fa['Embarcation'].str.upper() == eq_upper]
            if not df_eq_all.empty:
                dict_pronos[eq_upper] = df_eq_all['Temps_sec'].mean()
    return dict_pronos

@st.cache_data
def load_full_ergo_history():
    fichier_ergo = "donnees_ergo.csv"
    if not os.path.exists(fichier_ergo): return pd.DataFrame()
    try:
        df_e = pd.read_csv(fichier_ergo, sep=';', encoding='latin-1')
        def ergo_time_to_seconds(t):
            if pd.isna(t) or type(t) != str or ':' not in t: return None
            try:
                m, rest = t.split(':')
                return int(m) * 60 + float(rest.replace(',', '.'))
            except: return None
            
        df_e['Temps_sec'] = df_e['Temps'].apply(ergo_time_to_seconds)
        df_e['Date test'] = pd.to_datetime(df_e['Date test'], format='%d/%m/%Y', errors='coerce')
        df_e['Année'] = df_e['Date test'].dt.year
        df_e['Nom_Upper'] = df_e['Nom Prénom'].astype(str).str.upper().str.strip()
        df_e = df_e.dropna(subset=['Temps_sec', 'Date test', 'Nom Prénom'])
        return df_e
    except: return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_and_clean_crewtimer_data(regatta_id):
    url = f"https://www.crewtimer.com/results?asfile=true&regatta={regatta_id.strip()}"
    df_ct = pd.read_csv(url)
    df_ct.columns = [str(c).strip() for c in df_ct.columns]
    
    def extraire_equipage_strict(event_val):
        if pd.isna(event_val): return "INCONNU"
        txt = str(event_val).upper().strip()
        
        txt = txt.replace('J14', 'U15').replace('J16', 'U17').replace('J18', 'U19')
        
        match_start = re.search(r'(U\d+|S[HFM]|M[HFM]|PR\d+)', txt)
        if not match_start:
            return str(event_val).strip()
            
        start_idx = match_start.start()
        segment = txt[start_idx:start_idx+15].replace(" ", "")
        chunk = segment[:9]
        
        for _ in range(6):
            if len(chunk) < 3: break
            if re.search(r'\d(X|X\+|-|\+)$', chunk, re.IGNORECASE):
                return chunk
            chunk = chunk[:-1]
            
        return str(event_val).strip()
    
    def assembler_nom_equipage(row):
        crew = str(row.get('Crew', 'Bateau')).strip()
        stroke = str(row.get('Stroke', '')).strip()
        prenom_stroke = stroke.split(' ')[0] if stroke else ""
        return f"{crew} ({prenom_stroke})" if prenom_stroke else crew

    def Convert_ct_time(t):
        if pd.isna(t): return None
        t_str = str(t).strip()
        if t_str in ['DNS', 'DNF', 'EXC', '']: return None
        try:
            m, rest = t_str.split(':')
            return int(m) * 60 + float(rest.replace(',', '.'))
        except: return None

    if 'Event' in df_ct.columns:
        df_ct['Equipage'] = df_ct['Event'].apply(extraire_equipage_strict)
    else:
        df_ct['Equipage'] = "INCONNU"
        
    df_ct['Nom'] = df_ct.apply(assembler_nom_equipage, axis=1)
    if 'Place' in df_ct.columns:
        df_ct['Classement'] = pd.to_numeric(df_ct['Place'], errors='coerce')
    else:
        df_ct['Classement'] = None
        
    df_ct['Realise_sec'] = df_ct['RawTime'].apply(Convert_ct_time) if 'RawTime' in df_ct.columns else None
    
    df_ct_valid = df_ct.dropna(subset=['Realise_sec', 'Classement']).copy()
    df_ct_valid = df_ct_valid[df_ct_valid['Realise_sec'] >= 150]
    
    return df_ct_valid

def seconds_to_time(s):
    if pd.isna(s) or s is None: return ""
    m = int(s // 60)
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

# Chargement global stable
df = load_data()
dict_pronos_global = get_pronos_dict(df)
df_ergo_full = load_full_ergo_history()

# ==========================================
# 1. EN-TÊTE CONFIGURATION 
# ==========================================
col_titre, col_espace, col_recherche = st.columns([3, 1, 2])

with col_titre:
    st.title("🚣‍♂️ Tableau de Bord - Aviron")

with col_recherche:
    colonnes_rameurs = [f'Rameur{i}' for i in range(1, 9)] + ['Barreur']
    tous_les_rameurs = pd.concat([df[col] for col in colonnes_rameurs]).dropna().unique()
    tous_les_rameurs = sorted([r for r in tous_les_rameurs if str(r).strip() != ""])

    recherche_rameur = st.multiselect(
        "🔍 Recherche Rameur :", 
        options=tous_les_rameurs,
        placeholder="Tapez un nom/prénom..."
    )

# ==========================================
# MODE PROFIL INDIVIDUEL 
# ==========================================
if recherche_rameur:
    for rameur in recherche_rameur:
        st.markdown(f"## 👤 Profil Athlète : {rameur}")
        
        st.markdown("### 🚣‍♂️ Historique Bateau")
        mask_rameur = df[colonnes_rameurs].isin([rameur]).any(axis=1)
        df_historique = df[mask_rameur]
        
        colonnes_historique = ['Année', 'Discipline', 'Championnat', 'Catégorie', 'Embarcation', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau', 'Club'] + colonnes_rameurs
        df_historique_trie = df_historique[colonnes_historique].sort_values(by=['Année', 'Embarcation', 'Finale', 'Position'], ascending=[False, True, True, True])
        st.dataframe(df_historique_trie, use_container_width=True, hide_index=True)
        
        if not df_ergo_full.empty:
            parts = set(strip_accents(rameur).split())
            mask_ergo = df_ergo_full['Nom_Upper'].apply(lambda x: parts.issubset(set(strip_accents(x).split())))
            df_ergo_rameur = df_ergo_full[mask_ergo]
            
            if not df_ergo_rameur.empty:
                st.markdown("### 💪 Historique Ergomètre (Record annuel)")
                best_ergo_annee = df_ergo_rameur.groupby('Année')['Temps_sec'].min().reset_index()
                best_ergo_annee['Temps_Affiche'] = pd.to_datetime(best_ergo_annee['Temps_sec'], unit='s')
                
                c_graph_ergo, c_table_ergo = st.columns([2, 1])
                with c_graph_ergo:
                    fig_ergo = px.line(best_ergo_annee, x='Année', y='Temps_Affiche', markers=True)
                    fig_ergo.update_yaxes(tickformat="%M:%S", autorange="reversed", title="Temps (Min:Sec)")
                    fig_ergo.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig_ergo, use_container_width=True)
                with c_table_ergo:
                    df_ergo_table = df_ergo_rameur[['Date test', 'Temps', 'Moy./500', 'Puiss.']].sort_values(by='Date test', ascending=False)
                    df_ergo_table['Date test'] = df_ergo_table['Date test'].dt.strftime('%d/%m/%Y')
                    st.dataframe(df_ergo_table, use_container_width=True, hide_index=True, height=250)
        st.markdown("<hr>", unsafe_allow_html=True)
    st.info("💡 Retirez les noms de la barre de recherche en haut à droite pour revenir au tableau de bord général.")

# ==========================================
# MODE TABLEAU DE BORD GÉNÉRAL
# ==========================================
else:
    disciplines_presentes = [d for d in ["RIVIERE", "MER", "LONGUE DISTANCE", "PR", "UNSS/FFSU", "BRS", "INDOOR"] if d in df['Discipline'].unique()]
    
    cf0, cf1, cf2, cf3, cf4, cf5, cf6 = st.columns([1.5, 1.2, 1.5, 1.2, 1.5, 1.2, 1.2])
    
    with cf0:
        discipline_choisie = st.selectbox("Discipline", options=disciplines_presentes)
        
    is_longue_distance = (discipline_choisie == "LONGUE DISTANCE")
    df_discipline = df[df['Discipline'] == discipline_choisie].copy()
    df_cascade = df_discipline.copy()

    with cf1:
        annees_dispos = sorted(df_cascade['Année'].dropna().unique(), reverse=True)
        filter_annee = st.multiselect("Année", annees_dispos)
    if filter_annee: df_cascade = df_cascade[df_cascade['Année'].isin(filter_annee)]

    with cf2:
        groupes_cat = {"SENIOR": ["SENIORS", "CRITERIUM", "SPRINTS", "SPRINTS CRITERIUM", "SPRINTS 1000m"], "U17": ["U17", "U17 ELITE"]}
        cat_to_groupe = {c: grp for grp, cats in groupes_cat.items() for c in cats}
        df_cascade['Groupe_Cat'] = df_cascade['Catégorie'].apply(lambda x: cat_to_groupe.get(x, x))
        groupes_dispos = sorted(df_cascade['Groupe_Cat'].dropna().unique())
        
        filter_groupe = st.multiselect("Catégorie", groupes_dispos)
        cats_to_keep = []
        if filter_groupe:
            sous_cats_possibles = []
            for g in filter_groupe:
                if g in groupes_cat: sous_cats_possibles.extend(groupes_cat[g])
                else: cats_to_keep.append(g) 
            if sous_cats_possibles:
                sous_cats_dispos = sorted(df_cascade[df_cascade['Catégorie'].isin(sous_cats_possibles)]['Catégorie'].unique())
                if sous_cats_dispos:
                    if discipline_choisie == "RIVIERE":
                        filter_sous_cat = st.multiselect("Sous-catégories", sous_cats_dispos, default=sous_cats_dispos)
                        cats_to_keep.extend(filter_sous_cat)
                    else: cats_to_keep.extend(sous_cats_dispos)
            if cats_to_keep: df_cascade = df_cascade[df_cascade['Catégorie'].isin(cats_to_keep)]
            else: df_cascade = df_cascade.iloc[0:0] 
    filter_cat = df_cascade['Catégorie'].unique() if filter_groupe else []

    with cf3:
        embs_dispos = sorted(df_cascade['Embarcation'].dropna().unique())
        filter_emb = st.multiselect("Embarcation", embs_dispos)
    if filter_emb: df_cascade = df_cascade[df_cascade['Embarcation'].isin(filter_emb)]

    with cf4:
        # ✅ Filtre clubs propre : Extrait les noms individuels des colonnes Club1 à Club4
        colonnes_recherche_clubs = ['Club1', 'Club2', 'Club3', 'Club4']
        clubs_uniques = pd.concat([df_cascade[c] for c in colonnes_recherche_clubs]).dropna().unique()
        clubs_dispos = sorted([str(c) for c in clubs_uniques if str(c).strip() != ""])
        
        filter_club = st.multiselect("Club", clubs_dispos)
        
    if filter_club: 
        # ✅ Applique le filtre en cherchant si le club sélectionné est PRÉSENT dans Club1, 2, 3 ou 4
        mask_club = df_cascade[colonnes_recherche_clubs].isin(filter_club).any(axis=1)
        df_cascade = df_cascade[mask_club]

    with cf5:
        finales_dispos = sorted(df_cascade['Finale'].dropna().unique())
        filter_finale = st.multiselect("Finale", finales_dispos)
    if filter_finale: df_cascade = df_cascade[df_cascade['Finale'].isin(filter_finale)]

    with cf6:
        dist_dispos = sorted(df_cascade['Distance'].dropna().unique())
        filter_dist = st.multiselect("Distance", dist_dispos)
    if filter_dist: df_cascade = df_cascade[df_cascade['Distance'].isin(filter_dist)]

    df_filtre = df_cascade

    st.markdown("<hr style='border: none; height: 1px; background: linear-gradient(90deg, rgba(210,210,210,1) 0%, rgba(210,210,210,0) 100%); margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

    if len(filter_emb) == 1:
        emb_selectionnee = filter_emb[0]
        
        col_t, col_btn1, col_btn2 = st.columns([6, 1.5, 1.5])
        with col_t: st.markdown(f"### 📈 Analyse : {emb_selectionnee}")
        with col_btn1: afficher_podium = st.toggle("🏆 Mode Podium")
        with col_btn2: afficher_ergo = st.toggle("💪 Superposer Ergo")

        df_emb = df_discipline[df_discipline['Embarcation'] == emb_selectionnee].copy()
        if len(filter_cat) > 0: df_emb = df_emb[df_emb['Catégorie'].isin(filter_cat)]

        fig1 = None
        podiums = df_emb[(df_emb['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_emb['Position'] <= 3)]
        if not podiums.empty:
            if is_longue_distance:
                evo_eau = podiums.groupby(['Année', 'Distance'])['Temps_sec'].mean().reset_index().sort_values('Année')
                evo_eau['Axe_X'] = evo_eau['Année'].astype(str) + " (" + evo_eau['Distance'].astype(str) + ")"
                evo_ergo = podiums.dropna(subset=['Moyenne_Ergo_sec']).groupby(['Année', 'Distance'])['Moyenne_Ergo_sec'].mean().reset_index()
                evo_ergo['Axe_X'] = evo_ergo['Année'].astype(str) + " (" + evo_ergo['Distance'].astype(str) + ")"
            else:
                evo_eau = podiums.groupby('Année')['Temps_sec'].mean().reset_index().sort_values('Année')
                evo_eau['Axe_X'] = evo_eau['Année'].astype(str)
                evo_ergo = podiums.dropna(subset=['Moyenne_Ergo_sec']).groupby('Année')['Moyenne_Ergo_sec'].mean().reset_index()
                evo_ergo['Axe_X'] = evo_ergo['Année'].astype(str)

            evo_combined = pd.merge(evo_eau, evo_ergo[['Axe_X', 'Moyenne_Ergo_sec']], on='Axe_X', how='left')
            evo_combined['Temps_Eau_Affiche'] = pd.to_datetime(evo_combined['Temps_sec'], unit='s')
            evo_combined['Temps_Ergo_Affiche'] = pd.to_datetime(evo_combined['Moyenne_Ergo_sec'], unit='s')

            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(x=evo_combined['Axe_X'], y=evo_combined['Temps_Eau_Affiche'], mode='lines+markers', name="Eau", line=dict(color='royalblue', width=3), hovertemplate="<b>%{x}</b><br>Eau: %{y|%M:%S}<extra></extra>"))
            if afficher_ergo and not evo_combined['Moyenne_Ergo_sec'].isna().all():
                fig1.add_trace(go.Scatter(x=evo_combined['Axe_X'], y=evo_combined['Temps_Ergo_Affiche'], mode='lines+markers', name="Ergo", line=dict(color='darkorange', width=2, dash='dash'), hovertemplate="<b>%{x}</b><br>Ergo: %{y|%M:%S}<extra></extra>"))
            fig1.update_layout(yaxis=dict(tickformat="%M:%S", autorange="reversed", title=""), xaxis=dict(type='category', categoryorder='array', categoryarray=evo_combined['Axe_X']), height=240, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        fig2 = None
        finales_cibles = ['FA', 'FB', 'FC', 'FD']
        df_finales = df_emb[df_emb['Finale'].isin(finales_cibles)]
        if not df_finales.empty:
            if is_longue_distance:
                evo_finales = df_finales.groupby(['Année', 'Distance', 'Finale'])['Temps_sec'].mean().reset_index()
                evo_finales['Axe_X'] = evo_finales['Année'].astype(str) + " (" + evo_finales['Distance'].astype(str) + ")"
            else:
                evo_finales = df_finales.groupby(['Année', 'Finale'])['Temps_sec'].mean().reset_index()
                evo_finales['Axe_X'] = evo_finales['Année'].astype(str)
            evo_finales['Temps_Affiche'] = pd.to_datetime(evo_finales['Temps_sec'], unit='s')
            evo_finales['Finale'] = pd.Categorical(evo_finales['Finale'], categories=finales_cibles, ordered=True)
            evo_finales = evo_finales.sort_values(['Finale', 'Année'])
            fig2 = px.line(evo_finales, x='Axe_X', y='Temps_Affiche', color='Finale', markers=True)
            fig2.update_yaxes(tickformat="%M:%S", autorange="reversed", title="")
            fig2.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

        def render_pronos_and_table():
            premiers_fa = df_emb[(df_emb['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_emb['Position'] == 1)]
            if not premiers_fa.empty:
                lignes_propres = []
                for annee, group in premiers_fa.groupby('Année'):
                    if len(group) > 1:
                        group_sans_mix = group[~group['Club'].str.contains('/', na=False)]
                        lignes_propres.append(group_sans_mix.sort_values('Temps_sec').head(1) if not group_sans_mix.empty else group.sort_values('Temps_sec').head(1))
                    else: lignes_propres.append(group)
                premiers_fa_filtres = pd.concat(lignes_propres)
                
                if not is_longue_distance:
                    premiers_fa_filtres['Année_Num'] = pd.to_numeric(premiers_fa_filtres['Année'], errors='coerce')
                    recents = premiers_fa_filtres[premiers_fa_filtres['Année_Num'] >= 2019]
                    cible = recents if not recents.empty else premiers_fa_filtres
                    t_eau = seconds_to_time(cible['Temps_sec'].mean())
                    t_ergo = seconds_to_time(cible['Moyenne_Ergo_sec'].mean()) if pd.notna(cible['Moyenne_Ergo_sec'].mean()) else "N/A"
                    
                    st.markdown(f"""
                        <div style="display: flex; gap: 8px; margin-bottom: 10px;">
                            <div style="flex: 1; background:#f8d7da; padding:6px; border-radius:4px; text-align:center;">
                                <span style="color:#721c24; font-size:0.75em; font-weight:bold; text-transform:uppercase;">🎯 Prono Bateau : </span>
                                <span style="color:#721c24; font-size:1.1em; font-weight:bold; margin-left:5px;">{t_eau}</span>
                            </div>
                            <div style="flex: 1; background:#fff3cd; padding:6px; border-radius:4px; text-align:center;">
                                <span style="color:#856404; font-size:0.75em; font-weight:bold; text-transform:uppercase;">💪 Moy. Ergo : </span>
                                <span style="color:#856404; font-size:1.1em; font-weight:bold; margin-left:5px;">{t_ergo}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("**Vainqueurs (FA)**")
                cols_to_show = ['Année', 'Distance', 'Club', 'Temps', 'Moyenne_Ergo_Bateau'] if is_longue_distance else ['Année', 'Club', 'Temps', 'Moyenne_Ergo_Bateau']
                liste_temps = premiers_fa_filtres[cols_to_show].sort_values(by='Année', ascending=False).rename(columns={'Moyenne_Ergo_Bateau': 'Ergo'})
                st.dataframe(liste_temps, hide_index=True, use_container_width=True, height=450 if not afficher_podium else 200)

        def render_club_podium():
            st.markdown("**🏆 Meilleurs Clubs**")
            top_equipes = df_filtre[(df_filtre['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_filtre['Position'] <= 3)]
            if not top_equipes.empty:
                colonnes_clubs_brutes = ['Club1', 'Club2', 'Club3', 'Club4']
                df_melt = top_equipes.melt(id_vars=['Position'], value_vars=colonnes_clubs_brutes, value_name='Nom_Club')
                df_melt = df_melt[df_melt['Nom_Club'].notna() & (df_melt['Nom_Club'] != "")]
                stats_clubs = df_melt.groupby('Nom_Club').agg(Podiums=('Position', 'count'), Position_Moyenne=('Position', 'mean')).reset_index()
                stats_clubs = stats_clubs.sort_values(by=['Podiums', 'Position_Moyenne'], ascending=[False, True]).head(3).to_dict('records')
                c_arg, c_or, c_bro = st.columns(3)
                def html_medal(c_data, bg, e, mt):
                    return f'<div style="margin-top:{mt}px; background:{bg}; padding:8px; border-radius:6px; text-align:center; color:black;"><h3 style="margin:0;">{e}</h3><div style="font-size:0.85em; font-weight:bold; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{c_data["Nom_Club"]}</div><div style="font-size:0.75em;">{c_data["Podiums"]} podiums</div></div>'
                if len(stats_clubs) > 0: c_or.markdown(html_medal(stats_clubs[0], "#FFD700", "🥇", 0), unsafe_allow_html=True)
                if len(stats_clubs) > 1: c_arg.markdown(html_medal(stats_clubs[1], "#E8E8E8", "🥈", 10), unsafe_allow_html=True)
                if len(stats_clubs) > 2: c_bro.markdown(html_medal(stats_clubs[2], "#CD7F32", "🥉", 20), unsafe_allow_html=True)

        if afficher_podium:
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                st.markdown("**Moyenne des Podiums**")
                if fig1: st.plotly_chart(fig1, use_container_width=True)
            with r1c2:
                st.markdown("**Évolution des Finales**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
            r2c1, r2c2 = st.columns(2)
            with r2c1: render_club_podium()
            with r2c2: render_pronos_and_table()
        else:
            c_graphes, c_droite = st.columns([2, 1])
            with c_graphes:
                st.markdown("**Moyenne des Podiums**")
                if fig1: st.plotly_chart(fig1, use_container_width=True)
                st.markdown("**Évolution des Finales**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
            with c_droite:
                render_pronos_and_table()
    else:
        st.info("💡 **Analyse Graphique** : Sélectionnez **une Embarcation** pour débloquer les courbes chronologiques empilées.")

    st.markdown("### 📊 Liste détaillée des résultats")
    colonnes_a_afficher = ['Année', 'Championnat', 'Catégorie', 'Embarcation', 'Club', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau']
    if is_longue_distance: colonnes_a_afficher.insert(4, 'Distance')

    df_trié = df_filtre.sort_values(by=['Année', 'Embarcation', 'Finale', 'Position'], ascending=[False, True, True, True])
    df_affichage = df_trié[colonnes_a_afficher].rename(columns={'Moyenne_Ergo_Bateau': 'Ergo Bateau'})

    event = st.dataframe(df_affichage, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if event and len(event.selection.rows) > 0:
        index_clique = event.selection.rows[0]
        ligne_selectionnee = df_trié.iloc[index_clique]
        ergo_info = f" (Ergo: {ligne_selectionnee['Moyenne_Ergo_Bateau']})" if pd.notna(ligne_selectionnee['Moyenne_Ergo_Bateau']) and str(ligne_selectionnee['Moyenne_Ergo_Bateau']).strip() != "" else ""
        st.info(f"🚣‍♂️ **Équipage : {ligne_selectionnee['Club']}** — {ligne_selectionnee['Embarcation']} (Finale {ligne_selectionnee['Finale']}){ergo_info}")
        equipiers = [f"**{col.replace('Rameur', 'Rameur ')}** : {ligne_selectionnee[col]}" for col in colonnes_rameurs if pd.notna(ligne_selectionnee[col]) and str(ligne_selectionnee[col]).strip() != ""]
        if equipiers:
            c_eq = st.columns(min(len(equipiers), 4))
            for i, eq in enumerate(equipiers): c_eq[i % 4].markdown(eq)

    # ==========================================
    # 6. ANALYSEUR CREWTIMER DIRECT (CACHÉ DANS UN EXPANDER)
    # ==========================================
    st.markdown("<hr style='border:none; height:1px; background:linear-gradient(90deg, rgba(200,200,200,1) 0%, rgba(200,200,200,0) 100%); margin:35px 0 15px 0;'>", unsafe_allow_html=True)
    
    with st.expander("⏱️ Analyseur de Régate en direct (CrewTimer)", expanded=False):
        regatta_id = st.text_input(
            "Identifiant CrewTimer de la régate (ex: r15899). Validez avec Entrée :", 
            placeholder="Entrez le code de la course et appuyez sur Entrée...", 
        )
            
        if regatta_id:
            try:
                with st.spinner("Analyse et calcul des pronostics en cours..."):
                    df_ct_base = load_and_clean_crewtimer_data(regatta_id)
                    
                    if not df_ct_base.empty:
                        df_ct_valid = df_ct_base.copy()
                        
                        dict_pronos_discipline = {}
                        for eq in df_ct_valid['Equipage'].dropna().unique():
                            eq_upper = str(eq).upper()
                            
                            if eq_upper.startswith('S'):
                                df_fa_s = df[(df['Finale'].isin(['FA', 'F', 'FINALE'])) & (df['Position'] == 1) & (df['Embarcation'].str.upper() == eq_upper)].copy()
                                df_fa_s['Année_Num'] = pd.to_numeric(df_fa_s['Année'], errors='coerce')
                                df_fa_s = df_fa_s[df_fa_s['Distance'].astype(str).str.contains('2000')]
                                
                                df_recents_s = df_fa_s[df_fa_s['Année_Num'] >= 2019]
                                if not df_recents_s.empty:
                                    dict_pronos_discipline[eq_upper] = df_recents_s['Temps_sec'].mean()
                                else:
                                    dict_pronos_discipline[eq_upper] = df_fa_s['Temps_sec'].mean() if not df_fa_s.empty else None
                            
                            else:
                                df_fa_disc = df_discipline[(df_discipline['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_discipline['Position'] == 1)].copy()
                                df_fa_disc['Année_Num'] = pd.to_numeric(df_fa_disc['Année'], errors='coerce')
                                df_recents_disc = df_fa_disc[df_fa_disc['Année_Num'] >= 2019]
                                
                                df_eq_recent = df_recents_disc[df_recents_disc['Embarcation'].str.upper() == eq_upper]
                                if not df_eq_recent.empty:
                                    dict_pronos_discipline[eq_upper] = df_eq_recent['Temps_sec'].mean()
                                else:
                                    df_eq_all = df_fa_disc[df_fa_disc['Embarcation'].str.upper() == eq_upper]
                                    dict_pronos_discipline[eq_upper] = df_eq_all['Temps_sec'].mean() if not df_eq_all.empty else None
                        
                        df_ct_valid['Equipage_Upper'] = df_ct_valid['Equipage'].str.upper()
                        df_ct_valid['Prono_sec'] = df_ct_valid['Equipage_Upper'].map(dict_pronos_discipline)
                        
                        df_ct_valid = df_ct_valid.dropna(subset=['Prono_sec'])
                        
                        if not df_ct_valid.empty:
                            df_ct_valid['% Prono_brut'] = (df_ct_valid['Prono_sec'] / df_ct_valid['Realise_sec']) * 100
                            df_ct_valid = df_ct_valid[df_ct_valid['% Prono_brut'] <= 115]
                            
                            if not df_ct_valid.empty:
                                max_prono_absolu = df_ct_valid['% Prono_brut'].max()
                                
                                equipages_dispos = sorted([str(e) for e in df_ct_valid['Equipage'].unique() if pd.notna(e)])
                                
                                col_f1, col_f2 = st.columns(2)
                                with col_f1:
                                    filtre_ct_eq = st.multiselect("Filtrer par type de bateau :", options=equipages_dispos)
                                with col_f2:
                                    filtre_ct_club = st.text_input("Filtrer par club / nom (ex: Bayonne) :", placeholder="Rechercher...")
                                    
                                if filtre_ct_eq:
                                    df_ct_valid = df_ct_valid[df_ct_valid['Equipage'].isin(filtre_ct_eq)]
                                
                                if filtre_ct_club:
                                    df_ct_valid = df_ct_valid[df_ct_valid['Nom'].str.contains(filtre_ct_club, case=False, na=False)]
                                
                                if not df_ct_valid.empty:
                                    df_ct_valid['% Prono'] = df_ct_valid['% Prono_brut'].apply(lambda x: f"{x:.2f}%")
                                    df_ct_valid['% Meilleur'] = df_ct_valid['% Prono_brut'].apply(lambda x: f"{(x / max_prono_absolu)*100:.2f}%")
                                    
                                    df_ct_valid['Temps réalisé'] = df_ct_valid['Realise_sec'].apply(seconds_to_time)
                                    df_ct_valid['Temps prono'] = df_ct_valid['Prono_sec'].apply(seconds_to_time)
                                    
                                    df_ct_final = df_ct_valid.sort_values(by='% Prono_brut', ascending=False)
                                    
                                    st.success(f"✅ Analyse connectée en temps réel. (Bateaux non reconnus et >115% ignorés)")
                                    cols_finales_affichage = ['Classement', 'Equipage', 'Nom', 'Temps réalisé', 'Temps prono', '% Prono', '% Meilleur']
                                    st.dataframe(df_ct_final[cols_finales_affichage], hide_index=True, use_container_width=True)
                                else:
                                    st.warning("Aucun équipage ne correspond aux filtres sélectionnés.")
                            else:
                                st.warning("Aucun résultat valide trouvé sous la barre des 115% de pronostic.")
                        else:
                            st.warning("Aucun équipage de cette course n'a pu être associé à un record dans la base.")
                    else:
                        st.warning("Aucun résultat exploitable ou aucun temps supérieur à 2m30 trouvé.")
            except Exception as e:
                st.error(f"Erreur d'aspiration réseau CrewTimer. Vérifiez l'identifiant (ex: r15899). Erreur technique : {e}")

    # ==========================================
    # 7. CALCULATEUR MOYENNE ERGOMÉTRIQUE
    # ==========================================
    with st.expander("💪 Calculateur Moyenne ergométrique", expanded=False):
        
        def process_custom_ergo():
            nom = st.session_state.get('custom_nom', '')
            m = st.session_state.get('custom_m', 0)
            s = st.session_state.get('custom_s', 0)
            cent = st.session_state.get('custom_cent', 0)
            
            if nom:
                nom_propre = f"{nom.strip()} (Perso)"
                temps_total = m * 60 + s + cent / 100.0
                st.session_state.custom_ergos[nom_propre] = {
                    'temps': temps_total,
                    'date': "Ajout manuel"
                }
                
                selection_actuelle = st.session_state.get("boat_selection", [])
                if nom_propre not in selection_actuelle:
                    st.session_state.boat_selection = selection_actuelle + [nom_propre]
                    
                st.session_state.custom_nom = ""
                st.session_state.custom_m = 0
                st.session_state.custom_s = 0
                st.session_state.custom_cent = 0
        
        st.markdown("**➕ Ajouter un ergo personnalisé**")
        col_nom, col_m, col_s, col_cent, col_btn = st.columns([3, 1, 1, 1, 2])
        
        with col_nom:
            st.text_input("Nom", placeholder="Ex: Rameur X", label_visibility="collapsed", key="custom_nom")
        with col_m:
            st.number_input("Min", min_value=0, max_value=60, step=1, label_visibility="collapsed", key="custom_m")
        with col_s:
            st.number_input("Sec", min_value=0, max_value=59, step=1, label_visibility="collapsed", key="custom_s")
        with col_cent:
            st.number_input("Cent", min_value=0, max_value=99, step=1, label_visibility="collapsed", key="custom_cent")
        with col_btn:
            st.button("Valider / Ajouter", on_click=process_custom_ergo, use_container_width=True)
            
        st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
        
        # --- CALCUL DE LA MOYENNE ---
        dict_ergo_calc = {}
        
        if not df_ergo_full.empty:
            df_ergo_recent = df_ergo_full.sort_values(by='Date test', ascending=False).drop_duplicates(subset=['Nom Prénom'])
            maintenant = pd.Timestamp.now()
            date_ref = maintenant if df_ergo_recent['Date test'].max() >= (maintenant - pd.DateOffset(years=1)) else df_ergo_recent['Date test'].max()
            df_ergo_valide = df_ergo_recent[df_ergo_recent['Date test'] >= (date_ref - pd.DateOffset(years=1))]
            
            dict_ergo_calc = {row['Nom Prénom']: {'temps': row['Temps_sec'], 'date': row['Date test'].strftime('%d/%m/%Y')} for _, row in df_ergo_valide.iterrows()}
        
        dict_ergo_calc.update(st.session_state.custom_ergos)
        
        if dict_ergo_calc:
            noms_dispos = sorted(list(dict_ergo_calc.keys()))
            
            selection_equipage = st.multiselect(
                "Sélectionnez les rameurs pour composer votre bateau :", 
                options=noms_dispos, 
                key="boat_selection",
                placeholder="Cherchez un rameur de la base ou un ajout manuel..."
            )
            
            if selection_equipage:
                t_sec = [dict_ergo_calc[nom]['temps'] for nom in selection_equipage]
                st.info(f"### Moyenne Ergo du bateau : {seconds_to_time(sum(t_sec) / len(t_sec))}")
                st.caption("Basé sur le test le plus récent de la base de données (ou sur les valeurs personnalisées ajoutées).")
                
                c_det = st.columns(min(len(selection_equipage), 4))
                for i, nom in enumerate(selection_equipage):
                    c_det[i % 4].markdown(f"**{nom}**<br>`{seconds_to_time(dict_ergo_calc[nom]['temps'])}`<br>*(le {dict_ergo_calc[nom]['date']})*", unsafe_allow_html=True)
        else:
            st.info("Aucune donnée disponible. Ajoutez des ergos manuellement ci-dessus.")

# Footer
st.markdown("<hr><div style='text-align: center; color: gray; font-size: 0.9em; padding-bottom: 20px;'>© 2026 Dashboard Aviron. Tous droits réservés.</div>", unsafe_allow_html=True)