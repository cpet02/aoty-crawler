    # Initialize genre selection in session state
    if 'selected_genre_tab' not in st.session_state:
        st.session_state.selected_genre_tab = 'search'
    if 'genre_search_value' not in st.session_state:
        st.session_state.genre_search_value = all_genres_list[0] if all_genres_list else ""
    if 'genre_hierarchy_value' not in st.session_state:
        st.session_state.genre_hierarchy_value = parent_genres_list[0] if parent_genres_list else ""
    
    # Tab-based genre selection
    tab1, tab2 = st.tabs(["🔍 Search", "📂 Browse Hierarchy"])
    
    with tab1:
        st.session_state.selected_genre_tab = 'search'
        # Search interface
        genre_search = st.text_input(
            "Search genres",
            placeholder="Type to filter (e.g., 'pop', 'wave', 'rock', 'ethereal')...",
            help="Find genres by typing keywords"
        )
        
        if genre_search:
            filtered_genre_list = sorted([g for g in all_genres_list if genre_search.lower() in g.lower()])
            st.caption(f"📍 Found {len(filtered_genre_list)} of {len(all_genres_list)} genres")
        else:
            filtered_genre_list = sorted(all_genres_list)
        
        st.session_state.genre_search_value = st.selectbox(
            "Select Genre",
            filtered_genre_list,
            index=0,
            help="Choose a specific genre or subgenre to scrape",
            key="genre_search_select"
        )
    
    with tab2:
        st.session_state.selected_genre_tab = 'hierarchy'
        # Hierarchical browsing
        st.caption("Browse parent genres and their subgenres:")
        
        selected_parent = st.selectbox(
            "Select Parent Genre",
            parent_genres_list,
            help="Choose a parent genre to see its subgenres",
            key="parent_select"
        )
        
        genre_info = get_genre_with_children(selected_parent)
        
        if genre_info["has_children"]:
            st.markdown(f"**Subgenres of {selected_parent}:** ({len(genre_info['children'])} available)")
            
            # Show subgenres as buttons in columns
            cols = st.columns(3)
            for idx, subgenre in enumerate(genre_info['children']):
                with cols[idx % 3]:
                    if st.button(subgenre, use_container_width=True, key=f"subgenre_btn_{subgenre}"):
                        st.session_state.genre_hierarchy_value = subgenre
            
            # Dropdown for subgenres
            st.session_state.genre_hierarchy_value = st.selectbox(
                "Or select from dropdown",
                genre_info['children'],
                index=0 if st.session_state.genre_hierarchy_value not in genre_info['children'] else genre_info['children'].index(st.session_state.genre_hierarchy_value),
                key="subgenre_dropdown"
            )
        else:
            st.info(f"ℹ️ {selected_parent} has no subgenres")
            st.session_state.genre_hierarchy_value = selected_parent
    
    # Use the correct genre based on which tab is active
    genre = st.session_state.genre_search_value if st.session_state.selected_genre_tab == 'search' else st.session_state.genre_hierarchy_value
