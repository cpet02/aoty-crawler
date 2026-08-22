"""
Shared album page extraction logic used by ComprehensiveAlbumSpider and ProductionSpider.
"""

import re


class AlbumExtractionMixin:
    """Mixin providing field-extraction helpers for an AOTY album page response."""

    def _extract_aoty_id(self, url):
        """Extract AOTY ID from URL"""
        # URL format: https://www.albumoftheyear.org/album/123456-album-name.php
        match = re.search(r'/album/(\d+-[^/]+)\.php', url)
        if match:
            return match.group(1)
        return None

    def _extract_album_title(self, response):
        """Extract album title"""
        selectors = [
            'h1.albumTitle span[itemprop="name"]::text',
            'meta[property="og:title"]::attr(content)',
            'h1::text',
        ]

        for selector in selectors:
            title = response.css(selector).get()
            if title:
                # Clean up if from og:title (Artist - Album format)
                if ' - ' in title:
                    title = title.split(' - ', 1)[1].strip()
                return title.strip()

        return None

    def _extract_artist_name(self, response):
        """Extract artist name"""
        selectors = [
            '[itemprop="byArtist"] span[itemprop="name"] a::text',
            '.artist a::text',
            'meta[property="og:title"]::attr(content)',
        ]

        for selector in selectors:
            artist = response.css(selector).get()
            if artist:
                # Clean up if from og:title (Artist - Album format)
                if ' - ' in artist:
                    artist = artist.split(' - ', 1)[0].strip()
                # Filter out non-artist names
                if artist.lower() not in ['discography', 'submit correction']:
                    return artist.strip()

        return None

    def _extract_release_date(self, response):
        """Extract release date"""
        detail_rows = response.css('.detailRow')
        for row in detail_rows:
            row_text = ' '.join(row.css('::text').getall())
            if 'Release Date' in row_text:
                date_match = re.search(r'>([A-Za-z]+)\s+(\d+),\s+(\d{4})<', row.get())
                if date_match:
                    month, day, year = date_match.groups()
                    return f"{month} {day}, {year}"

        # Fallback: try to extract from release links
        date_parts = response.css('.detailRow a[href*="/releases/"]::text').getall()
        if len(date_parts) >= 2:
            month = date_parts[0]
            year = date_parts[1].strip()
            detail_text = ' '.join(response.css('.detailRow::text').getall())
            day_match = re.search(r'(\d+),', detail_text)
            day = day_match.group(1) if day_match else "1"
            return f"{month} {day}, {year}"

        return None

    def _extract_critic_score(self, response):
        """Extract critic score"""
        score = response.css('[itemprop="ratingValue"] a::text').get()
        if score:
            try:
                return float(score)
            except ValueError:
                return None
        return None

    def _extract_user_score(self, response):
        """Extract user score"""
        score = response.css('.albumUserScore a::text').get()
        if score:
            try:
                return float(score)
            except ValueError:
                return None

        ratings = response.css('.rating::text').getall()
        for rating in ratings:
            if rating.strip() and rating.strip() != 'NR':
                try:
                    return float(rating.strip())
                except ValueError:
                    continue

        return None

    def _extract_critic_review_count(self, response):
        """Extract critic review count"""
        count = response.css('meta[itemprop="reviewCount"]::attr(content)').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass

        count = response.css('span[itemprop="ratingCount"]::text').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass

        text = response.css('.albumCriticScoreBox .numReviews::text').get()
        if text:
            match = re.search(r'(\d+)', text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

        return None

    def _extract_user_review_count(self, response):
        """Extract user review count"""
        # Look for strong tag inside numReviews (handles "1,234" -> 1234)
        text = response.css('.albumUserScoreBox .numReviews strong::text').get()
        if text:
            try:
                return int(text.replace(',', '').strip())
            except ValueError:
                pass

        # Alternative: extract from link text
        link_text = response.css('.albumUserScoreBox .numReviews a::text').get()
        if link_text:
            match = re.search(r'([\d,]+)', link_text)
            if match:
                try:
                    return int(match.group(1).replace(',', ''))
                except ValueError:
                    pass

        return None

    def _extract_genres(self, response):
        """Extract primary genres"""
        genres = []

        meta_genres = response.css('meta[itemprop="genre"]::attr(content)').getall()
        genres.extend(meta_genres)

        genre_links = response.css('.detailRow a[href*="/genre/"]::text').getall()
        for genre in genre_links:
            if genre and genre not in genres:
                genres.append(genre.strip())

        seen = set()
        unique_genres = []
        for genre in genres:
            if genre and genre not in seen:
                seen.add(genre)
                unique_genres.append(genre)

        return unique_genres if unique_genres else None

    def _extract_genre_tags(self, response):
        """Extract secondary genre tags"""
        tags = response.css('.detailRow .secondary::text').getall()
        if tags:
            return [tag.strip() for tag in tags if tag.strip()]
        return None

    def _extract_cover_image(self, response):
        """Extract cover image URL"""
        selectors = [
            '.albumTopBox.cover img::attr(src)',
            'meta[property="og:image"]::attr(content)',
            'img[alt*=" - "]::attr(src)',  # Alt text often contains "Artist - Album"
        ]

        for selector in selectors:
            image = response.css(selector).get()
            if image:
                return image

        return None

    def _extract_description(self, response):
        """Extract album description"""
        desc = response.css('meta[name="Description"]::attr(content)').get()
        if desc:
            return desc

        desc = response.css('meta[property="og:description"]::attr(content)').get()
        if desc:
            return desc

        return None

    def _extract_album_fields(self, response, album):
        """Populate an AlbumItem with all fields extracted from an album page response"""
        album['aoty_id'] = self._extract_aoty_id(response.url)
        album['title'] = self._extract_album_title(response)
        album['artist_name'] = self._extract_artist_name(response)
        album['release_date'] = self._extract_release_date(response)
        album['critic_score'] = self._extract_critic_score(response)
        album['user_score'] = self._extract_user_score(response)
        album['critic_review_count'] = self._extract_critic_review_count(response)
        album['user_review_count'] = self._extract_user_review_count(response)
        album['genres'] = self._extract_genres(response)
        album['genre_tags'] = self._extract_genre_tags(response)
        album['cover_image_url'] = self._extract_cover_image(response)
        album['description'] = self._extract_description(response)
        return album
