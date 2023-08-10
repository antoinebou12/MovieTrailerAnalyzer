import httpx
import os
import requests


class TMDBAPI:
    BASE_URL = "https://api.themoviedb.org/3"
    TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0, limits=httpx.Limits(max_keepalive_connections=0))
        if not self.TMDB_API_KEY:
            raise ValueError("TMDB API Key is missing!")

    async def _get_tmdb_data(self, endpoint, **params):
        """Utility method to fetch data from TMDB."""
        params["api_key"] = self.TMDB_API_KEY
        response = await self.client.get(f"{self.BASE_URL}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_popular_movies(self):
        data = await self._get_tmdb_data("movie/popular")
        return [movie["title"] for movie in data["results"][:25]]

    async def get_trailer_link(self, movie_name):
        # Use TMDB to get the official trailer link
        search_data = await self._get_tmdb_data("search/movie", query=movie_name)
        if search_data["results"]:
            movie_id = search_data["results"][0]["id"]
            video_data = await self._get_tmdb_data(f"movie/{movie_id}/videos")

            if main_trailers := [
                v
                for v in video_data["results"]
                if v["site"] == "YouTube"
                and (
                    "Official Trailer" in v["name"] or "Main Trailer" in v["name"]
                )
            ]:
                return f"https://www.youtube.com/watch?v={main_trailers[0]['key']}"
            if youtube_key := next((v["key"] for v in video_data["results"] if v["site"] == "YouTube"), None):
                return f"https://www.youtube.com/watch?v={youtube_key}"

        # If TMDB doesn't have a trailer link, fall back to YouTube search.
        # Note: We'll use synchronous `requests` library to get YouTube results 
        # since we're working within an async function.
        YOUTUBE_SEARCH_BASE_URL = "https://www.youtube.com/results"
        params = {"search_query": f"{movie_name} trailer"}
        response = requests.get(YOUTUBE_SEARCH_BASE_URL, params=params)
        soup = BeautifulSoup(response.text, "html.parser")
        link_element = soup.find("a", class_="yt-uix-tile-link")
        return f"https://www.youtube.com{link_element['href']}" if link_element else None

