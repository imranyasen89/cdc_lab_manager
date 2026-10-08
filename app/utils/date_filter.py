"""
Utility for unified date range filtering across CDC Lab Manager dashboards and reports.
Supports presets: today, yesterday, 7days, 30days, this_month, all, and custom date pickers.
"""
from datetime import datetime, date, timedelta
from app.utils.timezone import now_pkt

def get_date_range(preset=None, start_date_str=None, end_date_str=None, default_preset='today'):
    """
    Parses date range filters from request arguments.
    Returns: (start_dt, end_dt, start_date, end_date, active_preset, label)
    """
    today = now_pkt().date()
    
    # If custom dates provided without explicit preset, treat as custom
    if (start_date_str or end_date_str) and not preset:
        preset = 'custom'
    elif not preset:
        preset = default_preset
        
    preset = str(preset).lower().strip()
    
    if preset == 'today':
        start_date = today
        end_date = today
        label = f"Today ({today.strftime('%b %d, %Y')})"
    elif preset == 'yesterday':
        start_date = today - timedelta(days=1)
        end_date = today - timedelta(days=1)
        label = f"Yesterday ({start_date.strftime('%b %d, %Y')})"
    elif preset in ['7days', 'weekly']:
        preset = '7days'
        start_date = today - timedelta(days=6)
        end_date = today
        label = f"Last 7 Days ({start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')})"
    elif preset in ['30days', 'monthly']:
        preset = '30days'
        start_date = today - timedelta(days=29)
        end_date = today
        label = f"Last 30 Days ({start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')})"
    elif preset == 'this_month':
        start_date = today.replace(day=1)
        end_date = today
        label = f"This Month ({start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')})"
    elif preset == 'all':
        label = "All Time"
        return None, None, None, None, 'all', label
    elif preset == 'custom':
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today
        except (ValueError, TypeError):
            start_date = today
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
        except (ValueError, TypeError):
            end_date = today
            
        if start_date > end_date:
            start_date, end_date = end_date, start_date
            
        label = f"{start_date.strftime('%b %d, %Y')} – {end_date.strftime('%b %d, %Y')}"
    else:
        preset = 'today'
        start_date = today
        end_date = today
        label = f"Today ({today.strftime('%b %d, %Y')})"

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    return start_dt, end_dt, start_date, end_date, preset, label
