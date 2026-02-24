"""
Dynamic Genre Manager
Automatically discovers and persists new genres from scraped data
"""

import json
import os
from pathlib import Path
from genres_hierarchy import GENRE_HIERARCHY

# Path to persistent genre storage
GENRES_DB_PATH = Path(__file__).parent / "genres_db.json"

class GenresManager:
    """Manages dynamic genre discovery and persistence"""
    
    def __init__(self):
        self.genres_db = self._load_genres_db()
    
    def _load_genres_db(self):
        """Load genres database from file or create new one"""
        if GENRES_DB_PATH.exists():
            try:
                with open(GENRES_DB_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading genres DB: {e}")
                return self._create_default_db()
        else:
            return self._create_default_db()
    
    def _create_default_db(self):
        """Create default database from GENRE_HIERARCHY"""
        db = {
            "version": 1,
            "genres": {}
        }
        
        # Add all known genres from GENRE_HIERARCHY
        for parent, children in GENRE_HIERARCHY.items():
            db["genres"][parent] = {
                "type": "parent",
                "children": children,
                "discovered_at": "initial",
                "source": "hardcoded"
            }
            
            # Add children as well
            for child in children:
                if child not in db["genres"]:
                    db["genres"][child] = {
                        "type": "child",
                        "parent": parent,
                        "discovered_at": "initial",
                        "source": "hardcoded"
                    }
        
        # Add any genres from existing genres_db.json that are not in GENRE_HIERARCHY
        # This preserves auto-discovered genres from previous runs
        if GENRES_DB_PATH.exists():
            try:
                with open(GENRES_DB_PATH, 'r', encoding='utf-8') as f:
                    existing_db = json.load(f)
                    for genre_name, genre_data in existing_db.get("genres", {}).items():
                        if genre_name not in db["genres"]:
                            db["genres"][genre_name] = genre_data
            except Exception as e:
                print(f"Warning: Could not preserve existing genres: {e}")
        
        self._save_genres_db(db)
        return db
    
    def _save_genres_db(self, db=None):
        """Save genres database to file"""
        if db is None:
            db = self.genres_db
        
        try:
            with open(GENRES_DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving genres DB: {e}")
    
    def discover_genres_from_albums(self, albums):
        """
        Discover new genres from scraped album data
        
        Args:
            albums: List of album dictionaries with 'scrape_genre' and 'genres' fields
        
        Returns:
            dict with 'new_genres' and 'new_children' lists
        """
        new_genres = []
        new_children = []
        
        if not albums:
            return {"new_genres": new_genres, "new_children": new_children}
        
        for album in albums:
            # Check scrape_genre (parent genre used for scraping)
            scrape_genre = album.get('scrape_genre')
            if scrape_genre and scrape_genre not in self.genres_db["genres"]:
                new_genres.append(scrape_genre)
                self.add_genre(scrape_genre, genre_type="parent")
            
            # Check genres (actual genres from album page)
            genres = album.get('genres', [])
            for genre in genres:
                if genre not in self.genres_db["genres"]:
                    new_genres.append(genre)
                    # Try to infer parent if it matches a known parent
                    parent = self._infer_parent(genre, scrape_genre)
                    self.add_genre(genre, genre_type="child", parent=parent)
                    new_children.append(genre)
        
        return {
            "new_genres": list(set(new_genres)),
            "new_children": list(set(new_children))
        }
    
    def _infer_parent(self, genre, scrape_genre=None):
        """Try to infer parent genre for a new genre"""
        # If scrape_genre is a known parent, use it
        if scrape_genre and scrape_genre in self.genres_db["genres"]:
            if self.genres_db["genres"][scrape_genre].get("type") == "parent":
                return scrape_genre
        
        # Otherwise, return None (will be unassigned)
        return None
    
    def add_genre(self, genre_name, genre_type="parent", parent=None):
        """
        Add a new genre to the database
        
        Args:
            genre_name: Name of the genre
            genre_type: "parent" or "child"
            parent: Parent genre name (for child genres)
        """
        if genre_name in self.genres_db["genres"]:
            return  # Already exists
        
        from datetime import datetime
        
        if genre_type == "parent":
            self.genres_db["genres"][genre_name] = {
                "type": "parent",
                "children": [],
                "discovered_at": datetime.now().isoformat(),
                "source": "auto-discovered"
            }
        elif genre_type == "child":
            self.genres_db["genres"][genre_name] = {
                "type": "child",
                "parent": parent,
                "discovered_at": datetime.now().isoformat(),
                "source": "auto-discovered"
            }
            
            # Add to parent's children list if parent exists
            if parent and parent in self.genres_db["genres"]:
                if genre_name not in self.genres_db["genres"][parent].get("children", []):
                    self.genres_db["genres"][parent]["children"].append(genre_name)
        
        self._save_genres_db()
    
    def add_child_to_parent(self, parent_genre, child_genre):
        """Add a child genre to a parent genre"""
        if parent_genre not in self.genres_db["genres"]:
            self.add_genre(parent_genre, genre_type="parent")
        
        if child_genre not in self.genres_db["genres"]:
            self.add_genre(child_genre, genre_type="child", parent=parent_genre)
        else:
            # Update existing child's parent
            self.genres_db["genres"][child_genre]["parent"] = parent_genre
        
        # Add to parent's children list
        if "children" not in self.genres_db["genres"][parent_genre]:
            self.genres_db["genres"][parent_genre]["children"] = []
        
        if child_genre not in self.genres_db["genres"][parent_genre]["children"]:
            self.genres_db["genres"][parent_genre]["children"].append(child_genre)
        
        self._save_genres_db()
    
    def get_all_genres(self):
        """Get all genres (sorted)"""
        return sorted(list(self.genres_db["genres"].keys()))
    
    def get_parent_genres(self):
        """Get only parent genres (sorted)"""
        parents = [
            name for name, data in self.genres_db["genres"].items()
            if data.get("type") == "parent"
        ]
        return sorted(parents)
    
    def get_child_genres(self, parent):
        """Get child genres for a parent"""
        if parent not in self.genres_db["genres"]:
            return []
        return self.genres_db["genres"][parent].get("children", [])
    
    def get_genre_info(self, genre_name):
        """Get detailed info about a genre"""
        return self.genres_db["genres"].get(genre_name, {})
    
    def get_genre_with_children(self, parent):
        """Get parent genre with its children"""
        children = self.get_child_genres(parent)
        return {
            "parent": parent,
            "children": children,
            "has_children": len(children) > 0,
            "info": self.get_genre_info(parent)
        }
    
    def export_hierarchy(self):
        """Export current hierarchy as dict (for compatibility)"""
        hierarchy = {}
        for parent in self.get_parent_genres():
            hierarchy[parent] = self.get_child_genres(parent)
        return hierarchy
    
    def get_stats(self):
        """Get statistics about genres"""
        all_genres = self.genres_db["genres"]
        parents = [g for g in all_genres.values() if g.get("type") == "parent"]
        children = [g for g in all_genres.values() if g.get("type") == "child"]
        auto_discovered = [g for g in all_genres.values() if g.get("source") == "auto-discovered"]
        
        return {
            "total_genres": len(all_genres),
            "parent_genres": len(parents),
            "child_genres": len(children),
            "auto_discovered": len(auto_discovered),
            "hardcoded": len(all_genres) - len(auto_discovered)
        }


# Global instance
_manager = None

def get_manager():
    """Get or create the global GenresManager instance"""
    global _manager
    if _manager is None:
        _manager = GenresManager()
    return _manager

def discover_from_albums(albums):
    """Convenience function to discover genres from albums"""
    return get_manager().discover_genres_from_albums(albums)

def get_all_genres():
    """Get all genres"""
    return get_manager().get_all_genres()

def get_parent_genres():
    """Get parent genres"""
    return get_manager().get_parent_genres()

def get_child_genres(parent):
    """Get child genres for a parent"""
    return get_manager().get_child_genres(parent)

def get_genre_with_children(parent):
    """Get parent with children"""
    return get_manager().get_genre_with_children(parent)

def add_genre(genre_name, genre_type="parent", parent=None):
    """Add a new genre"""
    return get_manager().add_genre(genre_name, genre_type, parent)

def add_child_to_parent(parent_genre, child_genre):
    """Add child to parent"""
    return get_manager().add_child_to_parent(parent_genre, child_genre)

def get_stats():
    """Get genre statistics"""
    return get_manager().get_stats()
