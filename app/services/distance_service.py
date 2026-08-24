import math

class DistanceService:
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the great-circle distance between two points on the Earth's surface
        using the Haversine formula. Used as a local fallback when Maps API is not configured.
        Returns distance in kilometers.
        """
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 0.0
            
        # Earth radius in kilometers
        R = 6371.0
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        return round(distance, 2)
        
    @staticmethod
    def get_route_details(origin_lat, origin_lon, dest_lat, dest_lon):
        """
        Get travel details including estimated distance and travel time.
        Can be extended to query Google Maps Distance Matrix API.
        """
        distance_km = DistanceService.calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        
        # Estimate duration assuming average city rider speed of 30 km/h (0.5 km/min)
        duration_minutes = round(distance_km * 2)
        if duration_minutes < 1:
            duration_minutes = 1
            
        return {
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'provider': 'Haversine local estimation'
        }
