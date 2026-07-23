"""Service pour les calculs de décroissance radioactive."""
import math
from datetime import datetime, date
from typing import Optional

class DecayService:
    @staticmethod
    def calculate_activity(
        initial_activity: float,
        half_life_years: float,
        initial_date: date,
        current_date: date = None,
    ) -> float:
        """Calcule l'activité résiduelle en fonction de la période radioactive."""
        if current_date is None:
            current_date = date.today()

        delta_days = (current_date - initial_date).days
        half_life_days = half_life_years * 365.25
        decay_factor = math.exp(-math.log(2) * delta_days / half_life_days)
        return initial_activity * decay_factor
