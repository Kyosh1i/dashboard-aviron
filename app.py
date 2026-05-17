import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import unicodedata

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Dashboard Aviron", layout="wide", initial_sidebar_state="expanded")

# Réduction de l'espace vide tout en haut de la page
st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

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
def load_full_ergo_history():
    """Charge l'historique complet des ergos pour les profils individuels et le calculateur"""
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
    except Exception as e: return pd.DataFrame()

def seconds_to_time(s):
    if pd.isna(s): return ""
    m = int(s // 60)
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

df = load_data()
df_ergo_full = load_full_ergo_history()

# ==========================================
# 1. EN-TÊTE : TITRE ET RECHERCHE RAMEUR
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
# MODE 2 : VUE PROFIL RAMEUR (Si actif, cache le reste)
# ==========================================
if recherche_rameur:
    for rameur in recherche_rameur:
        st.markdown(f"## 👤 Profil Athlète : {rameur}")
        
        # --- A. Historique sur l'eau ---
        st.markdown("### 🚣‍♂️ Historique Bateau")
        mask_rameur = df[colonnes_rameurs].isin([rameur]).any(axis=1)
        df_historique = df[mask_rameur]
        
        colonnes_historique = ['Année', 'Discipline', 'Championnat', 'Catégorie', 'Embarcation', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau', 'Club'] + colonnes_rameurs
        df_historique_trie = df_historique[colonnes_historique].sort_values(
            by=['Année', 'Embarcation', 'Finale', 'Position'], 
            ascending=[False, True, True, True]
        )
        st.dataframe(df_historique_trie, use_container_width=True, hide_index=True)
        
        # --- B. Historique Ergomètre ---
        if not df_ergo_full.empty:
            parts = set(strip_accents(rameur).split())
            mask_ergo = df_ergo_full['Nom_Upper'].apply(lambda x: parts.issubset(set(strip_accents(x).split())))
            df_ergo_rameur = df_ergo_full[mask_ergo]
            
            if not df_ergo_rameur.empty:
                st.markdown("### 💪 Historique Ergomètre (Record annuel)")
                
                # On garde le meilleur temps de chaque année pour le graph
                best_ergo_annee = df_ergo_rameur.groupby('Année')['Temps_sec'].min().reset_index()
                best_ergo_annee['Temps_Affiche'] = pd.to_datetime(best_ergo_annee['Temps_sec'], unit='s')
                
                c_graph_ergo, c_table_ergo = st.columns([2, 1])
                
                with c_graph_ergo:
                    fig_ergo = px.line(best_ergo_annee, x='Année', y='Temps_Affiche', markers=True)
                    fig_ergo.update_yaxes(tickformat="%M:%S", autorange="reversed", title="Temps (Min:Sec)")
                    fig_ergo.update_traces(hovertemplate="<b>%{x}</b><br>Temps: %{y|%M:%S}<extra></extra>")
                    fig_ergo.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig_ergo, use_container_width=True)
                
                with c_table_ergo:
                    df_ergo_table = df_ergo_rameur[['Date test', 'Temps', 'Moy./500', 'Puiss.']].sort_values(by='Date test', ascending=False)
                    df_ergo_table['Date test'] = df_ergo_table['Date test'].dt.strftime('%d/%m/%Y')
                    st.dataframe(df_ergo_table, use_container_width=True, hide_index=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        
    st.info("💡 Retirez les noms de la barre de recherche en haut à droite pour revenir au tableau de bord général.")

# ==========================================
# MODE 1 : VUE PRINCIPALE (DASHBOARD)
# ==========================================
else:
    # --- FILTRES COMBINÉS ---
    c_disc, _ = st.columns([2, 8])
    with c_disc:
        disciplines_presentes = [d for d in ["RIVIERE", "MER", "LONGUE DISTANCE", "PR", "UNSS/FFSU", "BRS", "INDOOR"] if d in df['Discipline'].unique()]
        discipline_choisie = st.selectbox("Discipline :", options=disciplines_presentes, label_visibility="collapsed")
    
    # Séparateur sobre
    st.markdown("<hr style='border: none; height: 1px; background: linear-gradient(90deg, rgba(200,200,200,1) 0%, rgba(200,200,200,0) 100%); margin: 5px 0 15px 0;'>", unsafe_allow_html=True)

    is_longue_distance = (discipline_choisie == "LONGUE DISTANCE")
    df_discipline = df[df['Discipline'] == discipline_choisie].copy()
    
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    df_cascade = df_discipline.copy()

    with c1: 
        annees_dispos = sorted(df_cascade['Année'].dropna().unique(), reverse=True)
        filter_annee = st.multiselect("Année", annees_dispos)
    if filter_annee: df_cascade = df_cascade[df_cascade['Année'].isin(filter_annee)]

    with c2:
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

    with c3: 
        embs_dispos = sorted(df_cascade['Embarcation'].dropna().unique())
        filter_emb = st.multiselect("Embarcation", embs_dispos)
    if filter_emb: df_cascade = df_cascade[df_cascade['Embarcation'].isin(filter_emb)]

    with c4: 
        clubs_dispos = sorted(df_cascade['Club'].dropna().unique())
        filter_club = st.multiselect("Club", clubs_dispos)
    if filter_club: df_cascade = df_cascade[df_cascade['Club'].isin(filter_club)]

    with c5: 
        finales_dispos = sorted(df_cascade['Finale'].dropna().unique())
        filter_finale = st.multiselect("Finale", finales_dispos)
    if filter_finale: df_cascade = df_cascade[df_cascade['Finale'].isin(filter_finale)]

    with c6: 
        dist_dispos = sorted(df_cascade['Distance'].dropna().unique())
        filter_dist = st.multiselect("Distance", dist_dispos)
    if filter_dist: df_cascade = df_cascade[df_cascade['Distance'].isin(filter_dist)]

    df_filtre = df_cascade
    st.markdown("<br>", unsafe_allow_html=True)

    # --- ANALYSE ET GRAPHIQUES ---
    if len(filter_emb) == 1:
        emb_selectionnee = filter_emb[0]
        
        col_titre, col_b1, col_b2 = st.columns([6, 1.5, 1.5])
        with col_titre:
            st.markdown(f"### 📈 Analyse approfondie : {emb_selectionnee}")
        with col_b1:
            afficher_podium = st.toggle("🏆 Mode Podium")
        with col_b2:
            afficher_ergo = st.toggle("💪 Superposer Ergo")

        df_emb = df_discipline[df_discipline['Embarcation'] == emb_selectionnee].copy()
        if len(filter_cat) > 0: df_emb = df_emb[df_emb['Catégorie'].isin(filter_cat)]

        # --- PRÉPARATION DES GRAPHIQUES ---
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
            fig1.add_trace(go.Scatter(x=evo_combined['Axe_X'], y=evo_combined['Temps_Eau_Affiche'], mode='lines+markers', name="Temps Bateau", line=dict(color='royalblue', width=3), hovertemplate="<b>%{x}</b><br>Eau: %{y|%M:%S}<extra></extra>"))
            if afficher_ergo and not evo_combined['Moyenne_Ergo_sec'].isna().all():
                fig1.add_trace(go.Scatter(x=evo_combined['Axe_X'], y=evo_combined['Temps_Ergo_Affiche'], mode='lines+markers', name="Ergo Moyen", line=dict(color='darkorange', width=2, dash='dash'), hovertemplate="<b>%{x}</b><br>Ergo: %{y|%M:%S}<extra></extra>"))
            fig1.update_layout(yaxis=dict(tickformat="%M:%S", autorange="reversed", title="Temps (Min:Sec)"), xaxis=dict(type='category', categoryorder='array', categoryarray=evo_combined['Axe_X'], title=""), height=300, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

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
            fig2.update_yaxes(tickformat="%M:%S", title_text="Temps (Min:Sec)", autorange="reversed")
            fig2.update_xaxes(type='category')
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), xaxis_title="Année / Distance" if is_longue_distance else "Année", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig2.update_traces(hovertemplate="<b>Finale:</b> %{data.name}<br><b>%{x}</b><br><b>Temps:</b> %{y|%M:%S}<extra></extra>")

        # --- FONCTIONS AFFICHAGE COMPOSANTS ---
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
                
                # --- PRONOS COMPACTS EN HTML ---
                if not is_longue_distance:
                    premiers_fa_filtres['Année_Num'] = pd.to_numeric(premiers_fa_filtres['Année'], errors='coerce')
                    recents = premiers_fa_filtres[premiers_fa_filtres['Année_Num'] >= 2019]
                    cible = recents if not recents.empty else premiers_fa_filtres
                    
                    t_eau = seconds_to_time(cible['Temps_sec'].mean())
                    t_ergo = seconds_to_time(cible['Moyenne_Ergo_sec'].mean()) if pd.notna(cible['Moyenne_Ergo_sec'].mean()) else "N/A"
                    
                    st.markdown(f"""
                        <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                            <div style="flex: 1; background-color: #f8d7da; padding: 10px; border-radius: 5px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                <div style="color: #721c24; font-size: 0.8em; font-weight: bold; text-transform: uppercase;">🎯 Prono Bateau</div>
                                <div style="color: #721c24; font-size: 1.5em; font-weight: bold;">{t_eau}</div>
                            </div>
                            <div style="flex: 1; background-color: #fff3cd; padding: 10px; border-radius: 5px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                <div style="color: #856404; font-size: 0.8em; font-weight: bold; text-transform: uppercase;">💪 Moy. Ergo</div>
                                <div style="color: #856404; font-size: 1.5em; font-weight: bold;">{t_ergo}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                
                # --- TABLEAU ---
                st.markdown("**Temps des Vainqueurs (FA)**")
                cols_to_show = ['Année', 'Distance', 'Club', 'Temps', 'Moyenne_Ergo_Bateau'] if is_longue_distance else ['Année', 'Club', 'Temps', 'Moyenne_Ergo_Bateau']
                liste_temps = premiers_fa_filtres[cols_to_show].sort_values(by='Année', ascending=False).rename(columns={'Moyenne_Ergo_Bateau': 'Ergo'})
                # Hauteur dynamique pour s'adapter à l'espace
                st.dataframe(liste_temps, hide_index=True, use_container_width=True, height=500 if not afficher_podium else 250)

        def render_club_podium():
            st.markdown("**🏆 Podium des Clubs (1er à 3e)**")
            top_equipes = df_filtre[(df_filtre['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_filtre['Position'] <= 3)]
            if not top_equipes.empty:
                colonnes_clubs_brutes = ['Club1', 'Club2', 'Club3', 'Club4']
                df_melt = top_equipes.melt(id_vars=['Position'], value_vars=colonnes_clubs_brutes, value_name='Nom_Club')
                df_melt = df_melt[df_melt['Nom_Club'].notna() & (df_melt['Nom_Club'] != "")]
                stats_clubs = df_melt.groupby('Nom_Club').agg(Podiums=('Position', 'count'), Position_Moyenne=('Position', 'mean')).reset_index()
                stats_clubs = stats_clubs.sort_values(by=['Podiums', 'Position_Moyenne'], ascending=[False, True]).head(3).to_dict('records')

                c_arg, c_or, c_bro = st.columns(3)
                def html_medal(c_data, bg, e, mt):
                    return f'<div style="margin-top:{mt}px; background:{bg}; padding:10px; border-radius:8px; text-align:center;"><h2 style="margin:0;">{e}</h2><div style="font-size:0.9em; font-weight:bold; margin:5px 0;">{c_data["Nom_Club"]}</div><div style="font-size:0.8em;">{c_data["Podiums"]} podiums</div></div>'
                
                if len(stats_clubs) > 0: c_or.markdown(html_medal(stats_clubs[0], "#FFD700", "🥇", 0), unsafe_allow_html=True)
                if len(stats_clubs) > 1: c_arg.markdown(html_medal(stats_clubs[1], "#E8E8E8", "🥈", 15), unsafe_allow_html=True)
                if len(stats_clubs) > 2: c_bro.markdown(html_medal(stats_clubs[2], "#CD7F32", "🥉", 30), unsafe_allow_html=True)
            else: st.info("Aucun podium trouvé.")

        # --- LOGIQUE D'AFFICHAGE DU LAYOUT ---
        st.markdown("<hr style='margin: 0px 0 15px 0;'>", unsafe_allow_html=True)
        if afficher_podium:
            # Mode Podium (2x2)
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                st.markdown("**Temps moyen des Podiums**")
                if fig1: st.plotly_chart(fig1, use_container_width=True)
            with r1c2:
                st.markdown("**Évolution des Finales**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            r2c1, r2c2 = st.columns(2)
            with r2c1: render_club_podium()
            with r2c2: render_pronos_and_table()
        else:
            # Mode par défaut : Courbes superposées (2/3) et Table (1/3)
            c_graphes, c_droite = st.columns([2, 1])
            with c_graphes:
                st.markdown("**Temps moyen des Podiums**")
                if fig1: st.plotly_chart(fig1, use_container_width=True)
                st.markdown("**Évolution des Finales**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
            with c_droite:
                render_pronos_and_table()
    else:
        st.info("💡 **Analyse Graphique** : Sélectionnez **exactement une Embarcation** dans les filtres ci-dessus pour débloquer les graphiques.")

    # ==========================================
    # LISTE COMPLÈTE DES RÉSULTATS
    # ==========================================
    st.markdown("### 📊 Liste détaillée des résultats")
    colonnes_a_afficher = ['Année', 'Championnat', 'Catégorie', 'Embarcation', 'Club', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau']
    if is_longue_distance: colonnes_a_afficher.insert(4, 'Distance')

    df_trié = df_filtre.sort_values(by=['Année', 'Embarcation', 'Finale', 'Position'], ascending=[False, True, True, True])
    df_affichage = df_trié[colonnes_a_afficher].rename(columns={'Moyenne_Ergo_Bateau': 'Ergo Bateau'})

    event = st.dataframe(df_affichage, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if event and len(event.selection.rows) > 0:
        index_clique = event.selection.rows[0]
        ligne_selectionnee = df_trié.iloc[index_clique]
        ergo_info = f" (Ergo moyen: {ligne_selectionnee['Moyenne_Ergo_Bateau']})" if pd.notna(ligne_selectionnee['Moyenne_Ergo_Bateau']) and str(ligne_selectionnee['Moyenne_Ergo_Bateau']).strip() != "" else ""
        
        st.info(f"🚣‍♂️ **Équipage : {ligne_selectionnee['Club']}** — {ligne_selectionnee['Embarcation']} (Finale {ligne_selectionnee['Finale']}){ergo_info}")
        equipiers = [f"**{col.replace('Rameur', 'Rameur ')}** : {ligne_selectionnee[col]}" for col in colonnes_rameurs if pd.notna(ligne_selectionnee[col]) and str(ligne_selectionnee[col]).strip() != ""]
        if equipiers:
            c_eq = st.columns(min(len(equipiers), 4))
            for i, eq in enumerate(equipiers): c_eq[i % 4].markdown(eq)


    # ==========================================
    # CALCULATEUR D'ÉQUIPAGE (TOUT EN BAS)
    # ==========================================
    st.markdown("<hr style='margin: 40px 0 20px 0;'>", unsafe_allow_html=True)
    st.markdown("### ⏱️ Calculateur d'équipage personnalisé")
    
    if not df_ergo_full.empty:
        # On extrait le dernier test < 1 an pour le calculateur
        df_ergo_recent = df_ergo_full.sort_values(by='Date test', ascending=False).drop_duplicates(subset=['Nom Prénom'])
        maintenant = pd.Timestamp.now()
        date_ref = maintenant if df_ergo_recent['Date test'].max() >= (maintenant - pd.DateOffset(years=2)) else df_ergo_recent['Date test'].max()
        df_ergo_valide = df_ergo_recent[df_ergo_recent['Date test'] >= (date_ref - pd.DateOffset(years=2))]
        
        dict_ergo_calc = {row['Nom Prénom']: {'temps': row['Temps_sec'], 'date': row['Date test'].strftime('%d/%m/%Y')} for _, row in df_ergo_valide.iterrows()}
        
        noms_dispos = sorted(list(dict_ergo_calc.keys()))
        selection_equipage = st.multiselect("Sélectionnez les rameurs pour composer votre bateau :", options=noms_dispos, placeholder="Cherchez un rameur...")
        
        if selection_equipage:
            t_sec = [dict_ergo_calc[nom]['temps'] for nom in selection_equipage]
            st.success(f"### Moyenne Ergo du bateau : {seconds_to_time(sum(t_sec) / len(t_sec))}")
            st.caption("Basé sur le test le plus récent de chaque rameur (datant de moins d'un an).")
            
            c_det = st.columns(min(len(selection_equipage), 4))
            for i, nom in enumerate(selection_equipage):
                c_det[i % 4].markdown(f"**{nom}**<br>`{seconds_to_time(dict_ergo_calc[nom]['temps'])}`<br>*(le {dict_ergo_calc[nom]['date']})*", unsafe_allow_html=True)

# Footer

st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em; padding-bottom: 20px;'>
        © 2026 Dashboard Aviron. Tous droits réservés.<br>
        <i>Développé par <a href="https://www.linkedin.com/in/pierre-bourgeois-655464234" target="_blank" style="color: gray;">Pierre BOURGEOIS</a></i>
    </div>
    """, 
    unsafe_allow_html=True
)