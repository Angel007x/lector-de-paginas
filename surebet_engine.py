from pydantic import BaseModel
from typing import List, Optional

class OddsOption(BaseModel):
    bookmaker: str
    option_name: str
    odds: float

class EventMarkets(BaseModel):
    event_id: str
    sport: str
    match_name: str
    market_type: str
    options: List[OddsOption]

class OutcomeCalculated(BaseModel):
    bookmaker: str
    option_name: str
    odds: float
    stake_ratio: float

class SurebetOpportunity(BaseModel):
    event_id: str
    sport: str
    match_name: str
    market_type: str
    roi: float
    outcomes: List[OutcomeCalculated]

def calculate_surebet(event: EventMarkets, total_stake: float = 500.0) -> Optional[SurebetOpportunity]:
    # Evalúa pares de opciones de casas distintas (ej. Opción 1 en Casa A, Opción 2 en Casa B)
    if len(event.options) < 2:
        return None
    
    # Ejemplo básico para mercados de 2 opciones (1 vs 2)
    best_options = {}
    for opt in event.options:
        key = opt.option_name.upper().strip()
        if key not in best_options or opt.odds > best_options[key].odds:
            best_options[key] = opt
            
    selected = list(best_options.values())
    if len(selected) != 2:
        return None

    o1, o2 = selected[0], selected[1]
    arbitrage_index = (1 / o1.odds) + (1 / o2.odds)

    if arbitrage_index < 1.0:
        roi = ((1 / arbitrage_index) - 1) * 100
        
        ratio1 = (1 / o1.odds) / arbitrage_index
        ratio2 = (1 / o2.odds) / arbitrage_index

        outcomes = [
            OutcomeCalculated(bookmaker=o1.bookmaker, option_name=o1.option_name, odds=o1.odds, stake_ratio=ratio1),
            OutcomeCalculated(bookmaker=o2.bookmaker, option_name=o2.option_name, odds=o2.odds, stake_ratio=ratio2)
        ]

        return SurebetOpportunity(
            event_id=event.event_id,
            sport=event.sport,
            match_name=event.match_name,
            market_type=event.market_type,
            roi=roi,
            outcomes=outcomes
        )
    
    return None