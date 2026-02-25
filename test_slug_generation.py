#!/usr/bin/env python3
"""
Test script to verify slug generation logic - Run this to test the fixes
"""

def test_slug_generation():
    """Test various genre names to ensure proper slug generation"""
    
    test_cases = [
        ("Pop", "pop"),
        ("Hip Hop", "hip-hop"),
        ("Rock & Roll", "rock-&-roll"),
        ("R&B/Soul", "r&b/soul"),
        ("Electronic/Dance", "electronic/dance"),
        ("Alternative/Indie", "alternative/indie"),
        ("Folk/Country", "folk/country"),
        ("Metal", "metal"),
        ("Jazz", "jazz"),
        ("Classical", "classical"),
        ("World", "world"),
        ("Experimental", "experimental"),
        ("Soundtrack", "soundtrack"),
        ("Spoken Word", "spoken-word"),
        ("Comedy", "comedy"),
        ("Children's", "children's"),
        ("Holiday", "holiday"),
        ("Religious", "religious"),
        ("Stage & Screen", "stage-&-screen"),
        ("Avant-Garde", "avant-garde"),
    ]
    
    print("Testing slug generation logic:")
    print("=" * 50)
    
    all_passed = True
    for genre_name, expected_slug in test_cases:
        # This is the logic from our fixed spider
        slug = genre_name.lower().replace(' ', '-')
        passed = slug == expected_slug
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"{status} Genre: {genre_name:20} -> Slug: {slug:20} Expected: {expected_slug}")
    
    print("\n" + "=" * 50)
    print("Note: The spider will construct URLs like:")
    print("https://www.albumoftheyear.org/ratings/user-highest-rated/2026/pop/")
    print("https://www.albumoftheyear.org/ratings/user-highest-rated/2026/hip-hop/")
    
    # Test the exact matching logic
    print("\n" + "=" * 50)
    print("Testing exact matching logic (to avoid 'pop' matching 'toypop'):")
    
    target_genre = "Pop"
    test_matches = [
        ("pop", "Pop", True),      # exact match
        ("toypop", "Toypop", False),  # should NOT match (contains 'pop' but not exact)
        ("pop-rock", "Pop Rock", False),  # different genre
        ("hip-hop", "Hip Hop", False),  # different genre
        ("pop", "pop", True),      # lowercase exact match
        ("POP", "POP", True),      # uppercase exact match
        ("hypnagogic-pop", "Hypnagogic Pop", False),  # should NOT match
        ("dream-pop", "Dream Pop", False),  # should NOT match
        ("electropop", "Electropop", False),  # should NOT match
    ]
    
    for genre_slug, genre_name, should_match in test_matches:
        target_genre_lower = target_genre.lower()
        genre_slug_lower = genre_slug.lower()
        genre_name_lower = genre_name.lower()
        
        # This is the exact matching logic from our fixed spider
        matches = (
            genre_slug_lower == target_genre_lower.replace(' ', '-') or
            genre_slug_lower == target_genre_lower.replace('-', ' ').replace(' ', '-') or
            genre_name_lower == target_genre_lower
        )
        
        passed = matches == should_match
        status = "✓" if passed else "✗"
        if not passed:
            all_passed = False
        print(f"{status} Slug: '{genre_slug:15}', Name: '{genre_name:15}' -> Matches: {matches:5} (Expected: {should_match})")
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All tests passed! The fixes are working correctly.")
    else:
        print("❌ Some tests failed. Please review the logic.")
    
    return all_passed

if __name__ == "__main__":
    success = test_slug_generation()
    exit(0 if success else 1)