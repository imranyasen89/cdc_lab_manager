class LocationService:
    @staticmethod
    def get_map_config():
        """
        Returns map configuration.
        Provides structure to switch between Leaflet (default) and Google Maps.
        Centers map at G-8 Markaz, Islamabad.
        """
        return {
            'provider': 'leaflet',  # Toggle to 'google' if needed
            'google_api_key': None,  # Configure with environment variables
            'default_center': {
                'lat': 33.6811,
                'lng': 73.0361
            },
            'default_zoom': 13
        }
