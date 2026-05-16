import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# Configuration de la page
st.set_page_config(page_title="Dashboard Aviron", layout="wide", initial_sidebar_state="expanded")

# --- FONCTIONS DE PRÉPARATION ---
@st.cache_data
def load_data():
    df = pd.read_csv('base_donnees_aviron_enrichie.csv', sep=';')
    
    def time_to_seconds(t):
        if pd.isna(t) or type(t) != str or ':' not in t: return None
        try:
            m, s = t.split(':')
            return int(m) * 60 + float(s)
        except:
            return None
            
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
def load_ergo_data():
    """Charge les données ergo pour le calculateur (Garde le test le plus récent < 1 an)"""
    fichier_ergo = "donnees_ergo.csv"
    if not os.path.exists(fichier_ergo):
        return {}
    
    try:
        df_ergo = pd.read_csv(fichier_ergo, sep=';', encoding='latin-1')
        def ergo_time_to_seconds(t):
            if pd.isna(t) or type(t) != str or ':' not in t: return None
            try:
                m, rest = t.split(':')
                s = rest.replace(',', '.')
                return int(m) * 60 + float(s)
            except: return None
            
        df_ergo['Temps_sec'] = df_ergo['Temps'].apply(ergo_time_to_seconds)
        df_ergo['Date test'] = pd.to_datetime(df_ergo['Date test'], format='%d/%m/%Y', errors='coerce')
        
        # On supprime les lignes invalides
        df_ergo = df_ergo.dropna(subset=['Nom Prénom', 'Temps_sec', 'Date test'])
        
        # 1. On trie du plus récent au plus ancien
        df_ergo = df_ergo.sort_values(by='Date test', ascending=False)
        
        # 2. On garde uniquement le test le plus récent pour chaque rameur
        latest_ergo = df_ergo.drop_duplicates(subset=['Nom Prénom'])
        
        # 3. Filtre "Moins d'un an"
        maintenant = pd.Timestamp.now()
        # Sécurité : Si le fichier est vieux (ex: max date = 2020), on se base sur la date max du fichier
        date_reference = maintenant if latest_ergo['Date test'].max() >= (maintenant - pd.DateOffset(years=2)) else latest_ergo['Date test'].max()
        un_an_avant = date_reference - pd.DateOffset(years=2)
        
        latest_ergo_valide = latest_ergo[latest_ergo['Date test'] >= un_an_avant]
        
        # On crée le dictionnaire avec le temps ET la date
        dict_result = {}
        for _, row in latest_ergo_valide.iterrows():
            dict_result[row['Nom Prénom']] = {
                'temps': row['Temps_sec'],
                'date': row['Date test'].strftime('%d/%m/%Y')
            }
        return dict_result
    except Exception as e:
        return {}

def seconds_to_time(s):
    if pd.isna(s): return ""
    m = int(s // 60)
    sec = s % 60
    return f"{m:02d}:{sec:05.2f}"

df = load_data()

st.title("🚣‍♂️ Tableau de Bord - Résultats d'Aviron")
st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 1. SÉLECTION DE LA DISCIPLINE
# ==========================================
with st.container(border=True):
    st.markdown("### 🌊 1. Choix de la discipline")
    disciplines_presentes = [d for d in ["RIVIERE", "MER", "LONGUE DISTANCE", "PR", "UNSS/FFSU", "BRS", "INDOOR"] if d in df['Discipline'].unique()]

    discipline_choisie = st.selectbox(
        "Sélectionnez la discipline à analyser :",
        options=disciplines_presentes,
        label_visibility="collapsed"
    )

is_longue_distance = (discipline_choisie == "LONGUE DISTANCE")
df_discipline = df[df['Discipline'] == discipline_choisie].copy()


# ==========================================
# 2. RECHERCHE RAMEUR
# ==========================================
with st.container(border=True):
    st.markdown("### 🔍 2. Recherche par rameur")
    colonnes_rameurs = [f'Rameur{i}' for i in range(1, 9)] + ['Barreur']
    tous_les_rameurs = pd.concat([df[col] for col in colonnes_rameurs]).dropna().unique()
    tous_les_rameurs = sorted([r for r in tous_les_rameurs if str(r).strip() != ""])

    recherche_rameur = st.multiselect(
        "Rechercher l'historique d'un athlète (Cherche sur TOUTE la base) :", 
        options=tous_les_rameurs,
        placeholder="Commencez à taper un nom/prénom..."
    )

    if recherche_rameur:
        st.markdown(f"**Historique des courses pour : {', '.join(recherche_rameur)}**")
        
        mask_rameur = df[colonnes_rameurs].isin(recherche_rameur).any(axis=1)
        df_historique = df[mask_rameur]
        
        col_f_rameur1, col_f_rameur2 = st.columns(2)
        with col_f_rameur1:
            f_ram_disc = st.multiselect("Filtrer par Discipline :", sorted(df_historique['Discipline'].dropna().unique()))
        with col_f_rameur2:
            f_ram_cat = st.multiselect("Filtrer par Catégorie :", sorted(df_historique['Catégorie'].dropna().unique()))
            
        if f_ram_disc: df_historique = df_historique[df_historique['Discipline'].isin(f_ram_disc)]
        if f_ram_cat: df_historique = df_historique[df_historique['Catégorie'].isin(f_ram_cat)]
        
        colonnes_historique = ['Année', 'Discipline', 'Championnat', 'Catégorie', 'Embarcation', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau', 'Club'] + colonnes_rameurs
        df_historique_trie = df_historique[colonnes_historique].sort_values(
            by=['Année', 'Embarcation', 'Finale', 'Position'], 
            ascending=[False, True, True, True]
        )
        
        st.dataframe(df_historique_trie, use_container_width=True, hide_index=True)


# ==========================================
# 3. CALCULATEUR D'ÉQUIPAGE ERGO
# ==========================================
with st.container(border=True):
    st.markdown("### ⏱️ 3. Calculateur d'équipage personnalisé")
    afficher_calculateur = st.toggle("🧮 Ouvrir le calculateur de moyenne Ergo")
    
    if afficher_calculateur:
        dict_ergo = load_ergo_data()
        if dict_ergo:
            noms_dispos = sorted(list(dict_ergo.keys()))
            
            selection_equipage = st.multiselect(
                "Sélectionnez les rameurs pour composer votre bateau :",
                options=noms_dispos,
                placeholder="Cherchez un nom/prénom depuis la base fédérale..."
            )
            
            if selection_equipage:
                temps_equipage = [dict_ergo[nom]['temps'] for nom in selection_equipage]
                moyenne_sec = sum(temps_equipage) / len(temps_equipage)
                moy_str = seconds_to_time(moyenne_sec)
                
                st.success(f"### Moyenne du bateau : {moy_str}")
                st.caption("Basé sur le test le plus récent de chaque rameur (datant de moins d'un an).")
                
                # Affichage des temps individuels et de la date en dessous
                cols_detail = st.columns(min(len(selection_equipage), 4))
                for i, nom in enumerate(selection_equipage):
                    t_str = seconds_to_time(dict_ergo[nom]['temps'])
                    date_str = dict_ergo[nom]['date']
                    cols_detail[i % 4].markdown(f"**{nom}**<br>`{t_str}`<br>*(le {date_str})*", unsafe_allow_html=True)
        else:
            st.error("Aucun test ergo récent (moins d'un an) trouvé, ou fichier introuvable.")


# ==========================================
# 4. FILTRES DE LA COMPÉTITION
# ==========================================
with st.container(border=True):
    st.markdown(f"### 🎛️ 4. Filtres ({discipline_choisie})")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    df_cascade = df_discipline.copy()

    with c1: 
        annees_dispos = sorted(df_cascade['Année'].dropna().unique(), reverse=True)
        filter_annee = st.multiselect("Année", annees_dispos)
    if filter_annee: df_cascade = df_cascade[df_cascade['Année'].isin(filter_annee)]

    with c2:
        groupes_cat = {
            "SENIOR": ["SENIORS", "CRITERIUM", "SPRINTS", "SPRINTS CRITERIUM", "SPRINTS 1000m"],
            "U17": ["U17", "U17 ELITE"]
        }
        
        cat_to_groupe = {}
        for grp, cats in groupes_cat.items():
            for c in cats:
                cat_to_groupe[c] = grp

        df_cascade['Groupe_Cat'] = df_cascade['Catégorie'].apply(lambda x: cat_to_groupe.get(x, x))
        groupes_dispos = sorted(df_cascade['Groupe_Cat'].dropna().unique())
        
        filter_groupe = st.multiselect("Catégorie", groupes_dispos)
        
        cats_to_keep = []
        if filter_groupe:
            sous_cats_possibles = []
            for g in filter_groupe:
                if g in groupes_cat:
                    sous_cats_possibles.extend(groupes_cat[g])
                else:
                    cats_to_keep.append(g) 
                    
            if sous_cats_possibles:
                sous_cats_dispos = sorted(df_cascade[df_cascade['Catégorie'].isin(sous_cats_possibles)]['Catégorie'].unique())
                
                if sous_cats_dispos:
                    if discipline_choisie == "RIVIERE":
                        filter_sous_cat = st.multiselect("Sous-catégories", sous_cats_dispos, default=sous_cats_dispos)
                        cats_to_keep.extend(filter_sous_cat)
                    else:
                        cats_to_keep.extend(sous_cats_dispos)
                    
            if cats_to_keep:
                df_cascade = df_cascade[df_cascade['Catégorie'].isin(cats_to_keep)]
            else:
                df_cascade = df_cascade.iloc[0:0] 

    filter_cat = df_cascade['Catégorie'].unique() if filter_groupe else []

    with c3: 
        embs_dispos = sorted(df_cascade['Embarcation'].dropna().unique())
        filter_emb = st.multiselect("Embarcation", embs_dispos)
    if filter_emb: df_cascade = df_cascade[df_cascade['Embarcation'].isin(filter_emb)]

    with c4: 
        clubs_dispos = sorted(df_cascade['Club'].dropna().unique())
        filter_club = st.multiselect("Club", clubs_dispos)
    if filter_club:
        df_cascade = df_cascade[df_cascade['Club'].isin(filter_club)]

    with c5: 
        finales_dispos = sorted(df_cascade['Finale'].dropna().unique())
        filter_finale = st.multiselect("Finale", finales_dispos)
    if filter_finale: df_cascade = df_cascade[df_cascade['Finale'].isin(filter_finale)]

    with c6: 
        dist_dispos = sorted(df_cascade['Distance'].dropna().unique())
        filter_dist = st.multiselect("Distance", dist_dispos)
    if filter_dist: df_cascade = df_cascade[df_cascade['Distance'].isin(filter_dist)]

    df_filtre = df_cascade


# ==========================================
# 5. GRAPHIQUES, PRONO ET PODIUM
# ==========================================
with st.container(border=True):
    if len(filter_emb) == 1:
        emb_selectionnee = filter_emb[0]
        
        col_titre, col_b1, col_b2 = st.columns([4, 1.5, 1.5])
        with col_titre:
            st.markdown(f"### 📈 5. Analyse approfondie : {emb_selectionnee}")
        with col_b1:
            st.markdown("<br>", unsafe_allow_html=True)
            afficher_podium = st.toggle("🏆 Afficher le podium")
        with col_b2:
            st.markdown("<br>", unsafe_allow_html=True)
            afficher_ergo = st.toggle("💪 Superposer l'Ergo")

        df_emb = df_discipline[df_discipline['Embarcation'] == emb_selectionnee].copy()
        if len(filter_cat) > 0:
            df_emb = df_emb[df_emb['Catégorie'].isin(filter_cat)]

        # --- Graphique 1 : Podiums & ERGO ---
        fig1 = None
        podiums = df_emb[(df_emb['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_emb['Position'] <= 3)]
        
        if not podiums.empty:
            if is_longue_distance:
                evo_eau = podiums.groupby(['Année', 'Distance'])['Temps_sec'].mean().reset_index().sort_values('Année')
                evo_eau['Axe_X'] = evo_eau['Année'].astype(str) + " (" + evo_eau['Distance'].astype(str) + ")"
            else:
                evo_eau = podiums.groupby('Année')['Temps_sec'].mean().reset_index().sort_values('Année')
                evo_eau['Axe_X'] = evo_eau['Année'].astype(str)

            if is_longue_distance:
                evo_ergo = podiums.dropna(subset=['Moyenne_Ergo_sec']).groupby(['Année', 'Distance'])['Moyenne_Ergo_sec'].mean().reset_index()
                evo_ergo['Axe_X'] = evo_ergo['Année'].astype(str) + " (" + evo_ergo['Distance'].astype(str) + ")"
            else:
                evo_ergo = podiums.dropna(subset=['Moyenne_Ergo_sec']).groupby('Année')['Moyenne_Ergo_sec'].mean().reset_index()
                evo_ergo['Axe_X'] = evo_ergo['Année'].astype(str)

            evo_combined = pd.merge(evo_eau, evo_ergo[['Axe_X', 'Moyenne_Ergo_sec']], on='Axe_X', how='left')
            evo_combined['Temps_Eau_Affiche'] = pd.to_datetime(evo_combined['Temps_sec'], unit='s')
            evo_combined['Temps_Ergo_Affiche'] = pd.to_datetime(evo_combined['Moyenne_Ergo_sec'], unit='s')

            fig1 = go.Figure()
            
            fig1.add_trace(go.Scatter(
                x=evo_combined['Axe_X'], y=evo_combined['Temps_Eau_Affiche'],
                mode='lines+markers', name="Temps sur l'eau (Moy.)",
                line=dict(color='royalblue', width=3),
                hovertemplate="<b>%{x}</b><br>Eau: %{y|%M:%S}<extra></extra>"
            ))
            
            if afficher_ergo and not evo_combined['Moyenne_Ergo_sec'].isna().all():
                fig1.add_trace(go.Scatter(
                    x=evo_combined['Axe_X'], y=evo_combined['Temps_Ergo_Affiche'],
                    mode='lines+markers', name="Ergo Bateau (Moy.)",
                    line=dict(color='darkorange', width=2, dash='dash'),
                    hovertemplate="<b>%{x}</b><br>Ergo: %{y|%M:%S}<extra></extra>"
                ))

            fig1.update_layout(
                yaxis=dict(tickformat="%M:%S", autorange="reversed", title="Temps (Min:Sec)"),
                xaxis=dict(type='category', categoryorder='array', categoryarray=evo_combined['Axe_X'], title="Année / Distance" if is_longue_distance else "Année"),
                height=350, margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

        # --- Graphique 2 : Finales ---
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
            fig2.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Année / Distance" if is_longue_distance else "Année", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig2.update_traces(hovertemplate="<b>Finale:</b> %{data.name}<br><b>%{x}</b><br><b>Temps:</b> %{y|%M:%S}<extra></extra>")

        # --- Fonction : Meilleurs temps et Pronostics combinés ---
        def render_best_times():
            st.markdown("**Meilleurs temps (1ers de FA)**")
            premiers_fa = df_emb[(df_emb['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_emb['Position'] == 1)]
            
            if not premiers_fa.empty:
                lignes_propres = []
                for annee, group in premiers_fa.groupby('Année'):
                    if len(group) > 1:
                        group_sans_mix = group[~group['Club'].str.contains('/', na=False)]
                        if not group_sans_mix.empty:
                            lignes_propres.append(group_sans_mix.sort_values('Temps_sec').head(1))
                        else:
                            lignes_propres.append(group.sort_values('Temps_sec').head(1))
                    else:
                        lignes_propres.append(group)
                        
                premiers_fa_filtres = pd.concat(lignes_propres)
                
                cols_to_show = ['Année', 'Distance', 'Club', 'Temps', 'Moyenne_Ergo_Bateau'] if is_longue_distance else ['Année', 'Club', 'Temps', 'Moyenne_Ergo_Bateau']
                liste_temps = premiers_fa_filtres[cols_to_show].sort_values(by='Année', ascending=False)
                liste_temps = liste_temps.rename(columns={'Moyenne_Ergo_Bateau': 'Ergo Moyen'})
                
                st.dataframe(liste_temps, hide_index=True, use_container_width=True, height=230)
                
                if is_longue_distance:
                    st.warning("⚠️ Pronostics non applicables en Longue Distance.")
                else:
                    premiers_fa_filtres['Année_Num'] = pd.to_numeric(premiers_fa_filtres['Année'], errors='coerce')
                    premiers_recents = premiers_fa_filtres[premiers_fa_filtres['Année_Num'] >= 2019]
                    
                    if not premiers_recents.empty:
                        moyenne_historique_sec = premiers_recents['Temps_sec'].mean()
                        moyenne_ergo_sec = premiers_recents['Moyenne_Ergo_sec'].mean()
                        texte_prono = "depuis 2019"
                    else:
                        moyenne_historique_sec = premiers_fa_filtres['Temps_sec'].mean()
                        moyenne_ergo_sec = premiers_fa_filtres['Moyenne_Ergo_sec'].mean()
                        texte_prono = "sur tout l'historique"
                        
                    temps_prono = seconds_to_time(moyenne_historique_sec)
                    ergo_prono = seconds_to_time(moyenne_ergo_sec) if pd.notna(moyenne_ergo_sec) else "N/A"
                    
                    cp1, cp2 = st.columns(2)
                    with cp1:
                        st.error(f"**🎯 BATEAU (Prono)** \n### {temps_prono}")
                    with cp2:
                        st.warning(f"**💪 ERGO (Moy.)** \n### {ergo_prono}")
                        
                    st.caption(f"(Moyennes des premiers de la finale A {texte_prono})")
            else:
                st.warning("Aucun premier de FA trouvé.")

        # --- Fonction : Podium Clubs ---
        def render_club_podium():
            st.markdown("**Podium des Clubs (sur la sélection)**")
            top_equipes = df_filtre[(df_filtre['Finale'].isin(['FA', 'F', 'FINALE'])) & (df_filtre['Position'] <= 3)]
            
            if not top_equipes.empty:
                colonnes_clubs_brutes = ['Club1', 'Club2', 'Club3', 'Club4']
                df_melt = top_equipes.melt(id_vars=['Position'], value_vars=colonnes_clubs_brutes, value_name='Nom_Club')
                df_melt = df_melt[df_melt['Nom_Club'].notna() & (df_melt['Nom_Club'] != "")]
                
                stats_clubs = df_melt.groupby('Nom_Club').agg(
                    Podiums=('Position', 'count'),
                    Position_Moyenne=('Position', 'mean')
                ).reset_index()
                
                stats_clubs = stats_clubs.sort_values(by=['Podiums', 'Position_Moyenne'], ascending=[False, True]).head(3)
                clubs_list = stats_clubs.to_dict('records')

                def afficher_medaille(club_data, couleur_fond, emoji, marge_haut):
                    st.markdown(f"""
                    <div style="margin-top: {marge_haut}px; background-color: {couleur_fond}; padding: 10px; border-radius: 8px; text-align: center; color: black; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);">
                        <h1 style="margin: 0; font-size: 2rem; color: black;">{emoji}</h1>
                        <h3 style="margin: 5px 0; font-size: 1rem; color: black; word-wrap: break-word;">{club_data['Nom_Club']}</h3>
                        <p style="margin: 0; font-size: 0.9rem; color: black;"><b>{club_data['Podiums']}</b> podiums</p>
                    </div>
                    """, unsafe_allow_html=True)

                col_argent, col_or, col_bronze = st.columns(3)
                if len(clubs_list) > 0:
                    with col_or: afficher_medaille(clubs_list[0], "#FFD700", "🥇", 0)
                if len(clubs_list) > 1:
                    with col_argent: afficher_medaille(clubs_list[1], "#E8E8E8", "🥈", 20)
                if len(clubs_list) > 2:
                    with col_bronze: afficher_medaille(clubs_list[2], "#CD7F32", "🥉", 40)
            else:
                st.info("Aucun podium trouvé avec ces filtres.")

        # --- AFFICHAGE DE LA GRILLE ---
        if afficher_podium:
            r1_col1, r1_col2 = st.columns(2)
            with r1_col1:
                titre_graph1 = "**Temps moyen des Podiums (Eau vs Ergo)**" if afficher_ergo else "**Temps moyen des Podiums**"
                st.markdown(titre_graph1)
                if fig1: st.plotly_chart(fig1, use_container_width=True)
                else: st.warning("Pas assez de données de podiums.")
            with r1_col2:
                st.markdown("**Temps moyen par type de finale**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
                else: st.warning("Pas assez de données pour les finales.")
                
            st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
            r2_col1, r2_col2 = st.columns(2)
            with r2_col1: render_club_podium()
            with r2_col2: render_best_times()
                
        else:
            col_g, col_m, col_d = st.columns(3)
            with col_g:
                titre_graph1 = "**Temps moyen des Podiums (Eau vs Ergo)**" if afficher_ergo else "**Temps moyen des Podiums**"
                st.markdown(titre_graph1)
                if fig1: st.plotly_chart(fig1, use_container_width=True)
                else: st.warning("Pas assez de données de podiums.")
            with col_m:
                st.markdown("**Temps moyen par type de finale**")
                if fig2: st.plotly_chart(fig2, use_container_width=True)
                else: st.warning("Pas assez de données pour les finales.")
            with col_d: render_best_times()

    else:
        st.info("💡 **Analyse Graphique** : Sélectionnez **exactement une Embarcation** dans les filtres ci-dessus pour débloquer les graphiques d'évolution.")


# ==========================================
# 6. LISTE DES COURSES
# ==========================================
with st.container(border=True):
    st.markdown("### 📊 6. Liste détaillée des résultats")
    st.caption("👆 **Astuce : Cliquez sur la marge à gauche d'une ligne du tableau pour révéler la composition de l'équipage !**")

    colonnes_a_afficher = ['Année', 'Championnat', 'Catégorie', 'Embarcation', 'Club', 'Finale', 'Position', 'Temps', 'Moyenne_Ergo_Bateau']
    if is_longue_distance:
        colonnes_a_afficher.insert(4, 'Distance')

    df_trié = df_filtre.sort_values(
        by=['Année', 'Embarcation', 'Finale', 'Position'], 
        ascending=[False, True, True, True]
    )

    df_affichage = df_trié[colonnes_a_afficher].rename(columns={'Moyenne_Ergo_Bateau': 'Ergo Moyen Bateau'})

    event = st.dataframe(
        df_affichage, 
        use_container_width=True, 
        hide_index=True,
        on_select="rerun", 
        selection_mode="single-row"
    )

    # --- AFFICHAGE DE L'ÉQUIPAGE AU CLIC ---
    if event and len(event.selection.rows) > 0:
        index_clique = event.selection.rows[0]
        ligne_selectionnee = df_trié.iloc[index_clique]
        
        ergo_info = f" (Ergo moyen: {ligne_selectionnee['Moyenne_Ergo_Bateau']})" if pd.notna(ligne_selectionnee['Moyenne_Ergo_Bateau']) and str(ligne_selectionnee['Moyenne_Ergo_Bateau']).strip() != "" else ""
        
        st.info(f"🚣‍♂️ **Équipage : {ligne_selectionnee['Club']}** — {ligne_selectionnee['Embarcation']} (Finale {ligne_selectionnee['Finale']}){ergo_info}")
        
        equipiers = []
        for col in colonnes_rameurs:
            nom = ligne_selectionnee[col]
            if pd.notna(nom) and str(nom).strip() != "":
                titre_propre = col.replace('Rameur', 'Rameur ')
                equipiers.append(f"**{titre_propre}** : {nom}")
                
        if len(equipiers) > 0:
            colonnes_affichage = st.columns(min(len(equipiers), 4))
            for i, equipier in enumerate(equipiers):
                colonnes_affichage[i % 4].markdown(equipier)
        else:
            st.warning("Aucun équipage n'a été renseigné pour ce bateau dans la base de données.")


# --- PIED DE PAGE / COPYRIGHT ---

st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em; padding-bottom: 20px;'>
        © 2026 Dashboard Aviron. Tous droits réservés.<br>
        <i>Développé par <a href="https://www.linkedin.com/in/pierre-bourgeois-655464234" target="_blank" style="color: gray;">Pierre BOURGEOIS</a></i>
    </div>
    """, 
    unsafe_allow_html=True
)