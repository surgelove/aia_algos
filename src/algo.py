from collections import deque
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

import helper
import math
 
class TimeBasedStreamingMA:
    """
    Time-based streaming moving average calculator that uses actual timestamps
    instead of fixed number of data points. Supports SMA, EMA, DEMA, and TEMA.
    
    Key Features:
    - Uses time windows (e.g., "5 minutes", "1 hour") instead of row counts
    - Automatically handles irregular time intervals
    - Maintains time-weighted calculations
    - Supports all four MA types with time-based logic
    """
    
    def __init__(self, time_window, ma_type='SMA', alpha=None):
        """
        Initialize the time-based streaming moving average calculator.
        
        Parameters:
        -----------
        time_window : str or timedelta
            Time window for calculations (e.g., '5min', '1H', '30s')
            Can be pandas timedelta string or datetime.timedelta object
        ma_type : str
            Type of moving average: 'SMA', 'EMA', 'DEMA', 'TEMA'
        alpha : float, optional
            Smoothing factor for EMA. If None, calculated based on time window
        """
        self.ma_type = ma_type.upper()
        
        # Validate MA type
        if self.ma_type not in ['SMA', 'EMA', 'DEMA', 'TEMA']:
            raise ValueError("ma_type must be one of: 'SMA', 'EMA', 'DEMA', 'TEMA'")
        
        # Convert time window to timedelta
        if isinstance(time_window, str):
            # Handle common abbreviations and deprecated formats
            time_window_str = time_window.replace('H', 'h')  # Fix deprecated 'H' format
            self.time_window = pd.Timedelta(time_window_str)
        elif isinstance(time_window, timedelta):
            self.time_window = pd.Timedelta(time_window)
        else:
            raise ValueError("time_window must be a string (e.g., '5min') or timedelta object")
        
        # Store original time window specification
        self.time_window_str = str(time_window)
        
        # Calculate alpha for EMA-based calculations
        if alpha is None:
            # Convert time window to approximate number of periods for alpha calculation
            # Assume 1-minute base period for alpha calculation
            minutes = self.time_window.total_seconds() / 60
            equivalent_periods = max(1, minutes)  # At least 1 period
            self.alpha = 2.0 / (equivalent_periods + 1)
        else:
            if not (0 < alpha < 1):
                raise ValueError("alpha must be between 0 and 1")
            self.alpha = alpha
        
        # Initialize data storage - we need to keep all data within time window for SMA
        self.data_points = deque()  # Store (timestamp, price) tuples
        self.timestamps = deque()   # Store just timestamps for quick access
        
        # For EMA, DEMA, TEMA - maintain running calculations
        if self.ma_type != 'SMA':
            self.ema1 = None  # First EMA
            self.ema2 = None  # Second EMA (for DEMA, TEMA)
            self.ema3 = None  # Third EMA (for TEMA)
            self.initialized = False
            self.last_timestamp = None
        
        self.data_count = 0
        
    def _clean_old_data(self, current_timestamp):
        """Remove data points older than the time window."""
        cutoff_time = current_timestamp - self.time_window
        
        # Remove old data points
        while self.data_points and self.data_points[0][0] < cutoff_time:
            self.data_points.popleft()
            if self.timestamps:
                self.timestamps.popleft()
    
    def _calculate_time_weight(self, current_timestamp, last_timestamp):
        """Calculate time-based weight for EMA calculations."""
        if last_timestamp is None:
            return self.alpha
        
        # Calculate time elapsed in seconds
        time_elapsed = (current_timestamp - last_timestamp).total_seconds()
        
        # Handle edge cases
        if time_elapsed <= 0:
            return self.alpha  # No time elapsed, use base alpha
        
        # Assume base interval for alpha calculation (e.g., 60 seconds)
        base_interval = 60.0  # 1 minute
        
        # Adjust alpha based on actual time elapsed
        time_factor = time_elapsed / base_interval
        
        # Prevent issues with very small alpha values and large time factors
        if self.alpha <= 0 or self.alpha >= 1:
            return self.alpha
        
        # Apply time-weighted alpha: more time elapsed = more weight to new data
        try:
            adjusted_alpha = 1 - (1 - self.alpha) ** time_factor
            return min(1.0, max(0.0, adjusted_alpha))  # Clamp between 0 and 1
        except (ZeroDivisionError, OverflowError, ValueError):
            # Fallback to base alpha if calculation fails
            return self.alpha
    
    def add_data_point(self, timestamp, price):
        """
        Add a new data point and calculate the updated time-based moving average.
        
        Parameters:
        -----------
        timestamp : datetime or str
            Timestamp of the data point
        price : float
            Price value
            
        Returns:
        --------
        dict
            Dictionary containing current MA, time window info, and metadata
        """
        # Convert timestamp to datetime if it's a string
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        
        self.data_count += 1
        
        # Clean old data points outside time window
        self._clean_old_data(timestamp)
        
        # Add new data point
        self.data_points.append((timestamp, price))
        self.timestamps.append(timestamp)
        
        if self.ma_type == 'SMA':
            return self._calculate_time_sma(timestamp, price)
        elif self.ma_type == 'EMA':
            return self._calculate_time_ema(timestamp, price)
        elif self.ma_type == 'DEMA':
            return self._calculate_time_dema(timestamp, price)
        elif self.ma_type == 'TEMA':
            return self._calculate_time_tema(timestamp, price)
    
    def _calculate_time_sma(self, timestamp, price, return_full_window=False):
        """Calculate time-based Simple Moving Average."""
        # Calculate SMA using all data points within time window
        if len(self.data_points) == 0:
            current_ma = price
        else:
            total_price = sum(p for t, p in self.data_points)
            current_ma = total_price / len(self.data_points)
        
        if return_full_window:
            return {
                'timestamp': timestamp,
                'price': price,
                'moving_average': current_ma,
                'data_points_count': len(self.data_points),
                'time_window': self.time_window_str,
                'window_start': self.timestamps[0] if self.timestamps else timestamp,
                'window_end': timestamp,
                'time_span_actual': (timestamp - self.timestamps[0]).total_seconds() if self.timestamps else 0,
                'time_span_target': self.time_window.total_seconds(),
                'is_full_window': (timestamp - self.timestamps[0]) >= self.time_window if self.timestamps else False,
                'ma_type': 'Time-SMA'
            }
        return current_ma
    
    def _calculate_time_ema(self, timestamp, price, return_full_window=False):
        """Calculate time-based Exponential Moving Average."""
        if not self.initialized:
            # Initialize with first price
            self.ema1 = price
            self.initialized = True
            self.last_timestamp = timestamp
            time_weight = self.alpha
        else:
            # Calculate time-adjusted alpha
            time_weight = self._calculate_time_weight(timestamp, self.last_timestamp)
            # EMA calculation with time weighting
            self.ema1 = time_weight * price + (1 - time_weight) * self.ema1
            self.last_timestamp = timestamp
        
        if return_full_window:
            return {
                'timestamp': timestamp,
                'price': price,
                'moving_average': self.ema1,
                'data_points_count': self.data_count,
                'time_window': self.time_window_str,
                'window_start': self.timestamps[0] if self.timestamps else timestamp,
                'window_end': timestamp,
                'time_span_actual': (timestamp - self.timestamps[0]).total_seconds() if self.timestamps else 0,
                'time_span_target': self.time_window.total_seconds(),
                'is_full_window': (timestamp - self.timestamps[0]) >= self.time_window if self.timestamps else False,
                'ma_type': 'Time-EMA',
                'alpha_used': time_weight,
                'base_alpha': self.alpha
        }
        return self.ema1
        
    def _calculate_time_dema(self, timestamp, price, return_full_window=False):
        """Calculate time-based Double Exponential Moving Average."""
        if not self.initialized:
            # Initialize with first price
            self.ema1 = price
            self.ema2 = price
            self.initialized = True
            self.last_timestamp = timestamp
            time_weight = self.alpha
        else:
            # Calculate time-adjusted alpha
            time_weight = self._calculate_time_weight(timestamp, self.last_timestamp)
            # First EMA
            self.ema1 = time_weight * price + (1 - time_weight) * self.ema1
            # Second EMA (EMA of first EMA)
            self.ema2 = time_weight * self.ema1 + (1 - time_weight) * self.ema2
            self.last_timestamp = timestamp
        
        # DEMA = 2 * EMA1 - EMA2
        dema = 2 * self.ema1 - self.ema2
        
        if return_full_window:
            return {
                'timestamp': timestamp,
                'price': price,
                'moving_average': dema,
                'data_points_count': self.data_count,
                'time_window': self.time_window_str,
                'window_start': self.timestamps[0] if self.timestamps else timestamp,
                'window_end': timestamp,
                'time_span_actual': (timestamp - self.timestamps[0]).total_seconds() if self.timestamps else 0,
                'time_span_target': self.time_window.total_seconds(),
                'is_full_window': (timestamp - self.timestamps[0]) >= self.time_window if self.timestamps else False,
                'ma_type': 'Time-DEMA',
                'alpha_used': time_weight,
                'base_alpha': self.alpha,
                'ema1': self.ema1,
                'ema2': self.ema2
            }
        return dema
    
    def _calculate_time_tema(self, timestamp, price, return_full_window=False):
        """Calculate time-based Triple Exponential Moving Average."""
        if not self.initialized:
            # Initialize with first price
            self.ema1 = price
            self.ema2 = price
            self.ema3 = price
            self.initialized = True
            self.last_timestamp = timestamp
            time_weight = self.alpha
        else:
            # Calculate time-adjusted alpha
            time_weight = self._calculate_time_weight(timestamp, self.last_timestamp)
            # First EMA
            self.ema1 = time_weight * price + (1 - time_weight) * self.ema1
            # Second EMA (EMA of first EMA)
            self.ema2 = time_weight * self.ema1 + (1 - time_weight) * self.ema2
            # Third EMA (EMA of second EMA)
            self.ema3 = time_weight * self.ema2 + (1 - time_weight) * self.ema3
            self.last_timestamp = timestamp
        
        # TEMA = 3 * EMA1 - 3 * EMA2 + EMA3
        tema = 3 * self.ema1 - 3 * self.ema2 + self.ema3
        
        if return_full_window:
            return {
                'timestamp': timestamp,
                'price': price,
                'moving_average': tema,
                'data_points_count': self.data_count,
                'time_window': self.time_window_str,
                'window_start': self.timestamps[0] if self.timestamps else timestamp,
                'window_end': timestamp,
                'time_span_actual': (timestamp - self.timestamps[0]).total_seconds() if self.timestamps else 0,
                'time_span_target': self.time_window.total_seconds(),
                'is_full_window': (timestamp - self.timestamps[0]) >= self.time_window if self.timestamps else False,
                'ma_type': 'Time-TEMA',
                'alpha_used': time_weight,
                'base_alpha': self.alpha,
                'ema1': self.ema1,
                'ema2': self.ema2,
                'ema3': self.ema3
            }
        return tema
    
    def get_current_ma(self):
        """Get the current moving average without adding new data."""
        if self.ma_type == 'SMA':
            if len(self.data_points) == 0:
                return None
            total_price = sum(p for t, p in self.data_points)
            return total_price / len(self.data_points)
        else:
            if not self.initialized:
                return None
            if self.ma_type == 'EMA':
                return self.ema1
            elif self.ma_type == 'DEMA':
                return 2 * self.ema1 - self.ema2
            elif self.ma_type == 'TEMA':
                return 3 * self.ema1 - 3 * self.ema2 + self.ema3
    
    def get_time_window_info(self):
        """Get information about the current time window state."""
        current_time = self.timestamps[-1] if self.timestamps else None
        oldest_time = self.timestamps[0] if self.timestamps else None
        
        base_info = {
            'ma_type': f'Time-{self.ma_type}',
            'time_window_spec': self.time_window_str,
            'time_window_seconds': self.time_window.total_seconds(),
            'data_points_count': len(self.data_points),
            'total_data_processed': self.data_count,
            'current_ma': self.get_current_ma(),
            'oldest_timestamp': oldest_time,
            'newest_timestamp': current_time,
            'actual_time_span': (current_time - oldest_time).total_seconds() if current_time and oldest_time else 0,
            'window_utilization': ((current_time - oldest_time).total_seconds() / self.time_window.total_seconds() * 100) if current_time and oldest_time else 0
        }
        
        if self.ma_type != 'SMA':
            base_info.update({
                'base_alpha': self.alpha,
                'initialized': self.initialized,
                'last_calculation_time': self.last_timestamp
            })
            
            if self.initialized:
                if self.ma_type in ['EMA', 'DEMA', 'TEMA']:
                    base_info['ema1'] = self.ema1
                if self.ma_type in ['DEMA', 'TEMA']:
                    base_info['ema2'] = self.ema2
                if self.ma_type == 'TEMA':
                    base_info['ema3'] = self.ema3
        
        return base_info
    
    def reset(self):
        """Reset the moving average calculator."""
        self.data_count = 0
        self.data_points.clear()
        self.timestamps.clear()
        
        if self.ma_type != 'SMA':
            self.ema1 = None
            self.ema2 = None
            self.ema3 = None
            self.initialized = False
            self.last_timestamp = None


class Algo:
    """
    Time-based streaming moving average calculator that uses actual timestamps
    instead of fixed number of data points. Supports SMA, EMA, DEMA, and TEMA.
    
    Key Features:
    - Uses time windows (e.g., "5 minutes", "1 hour") instead of row counts
    - Automatically handles irregular time intervals
    - Maintains time-weighted calculations
    - Supports all four MA types with time-based logic
    """

    def __init__(self, base_interval, slow_interval, aspr_interval, peak_interval=None):

        self.base_ema_calc = TimeBasedStreamingMA(base_interval, ma_type='EMA')
        self.base_tema_calc = TimeBasedStreamingMA(base_interval, ma_type='TEMA')
        self.slow_ema_calc = TimeBasedStreamingMA(slow_interval, ma_type='EMA')
        self.slow_tema_calc = TimeBasedStreamingMA(slow_interval, ma_type='TEMA')
        self.aspr_ema_calc = TimeBasedStreamingMA(aspr_interval, ma_type='EMA')
        self.aspr_tema_calc = TimeBasedStreamingMA(aspr_interval, ma_type='TEMA')
        self.peak_ema_calc = TimeBasedStreamingMA(peak_interval, ma_type='EMA')
        self.peak_tema_calc = TimeBasedStreamingMA(peak_interval, ma_type='TEMA')
        self.peak_dema_calc = TimeBasedStreamingMA(peak_interval, ma_type='DEMA')

        self.peak_tamplitude_calculator = helper.TimeBasedMovement(range=1)

        # initialize the json that will hold timestamp price and ema values
        self.base_ema_values = []
        self.base_tema_values = []
        self.slow_ema_values = []
        self.slow_tema_values = []
        self.aspr_ema_values = []
        self.aspr_tema_values = []
        self.peak_ema_values = []
        self.peak_tema_values = []
        self.peak_dema_values = []

        self.base_direction = 0
        self.base_cross_price = None
        self.base_mamplitude = 0
        self.base_pamplitude = 0
        self.base_min_price_temp = np.inf
        self.base_max_price_temp = -np.inf
        self.base_min_price = None
        self.base_max_price = None

        self.peak_direction = 0
        self.peak_cross_price = None
        self.peak_pamplitude = 0
        self.peak_tamplitude = 0
        self.peak_follower_up = None
        self.peak_follower_dn = None
        self.peak_follower_distance = 0.0002

        self.aspr_direction = 0
        self.aspr_min_price_temp = np.inf
        self.aspr_max_price_temp = -np.inf
        self.aspr_min_price = None
        self.aspr_max_price = None
        self.aspr_min_price_previous = None
        self.aspr_max_price_previous = None
        self.aspr_sideways_count = 0


    def process_row(self, timestamp, price, precision, say):

        # region Moving Average
        # Calculate EMA and TEMA for the current price
        base_ema = round(self.base_ema_calc.add_data_point(timestamp, price), precision)
        base_tema = round(self.base_tema_calc.add_data_point(timestamp, price), precision)
        self.base_ema_values.append(base_ema)  # EMA value
        self.base_tema_values.append(base_tema)  # TEMA value

        aspr_ema = round(self.aspr_ema_calc.add_data_point(timestamp, price), precision)
        aspr_tema = round(self.aspr_tema_calc.add_data_point(timestamp, price), precision)
        self.aspr_ema_values.append(aspr_ema)
        self.aspr_tema_values.append(aspr_tema)

        peak_ema = round(self.peak_ema_calc.add_data_point(timestamp, price), precision)
        peak_tema = round(self.peak_tema_calc.add_data_point(timestamp, price), precision)
        peak_dema = round(self.peak_dema_calc.add_data_point(timestamp, price), precision)
        self.peak_ema_values.append(peak_ema)
        self.peak_tema_values.append(peak_tema)
        self.peak_dema_values.append(peak_dema)
        
        # Debugging values
        temp_value_1 = None
        temp_value_2 = None
        temp_value_3 = None
        temp_value_4 = None

        # endregion Moving Average

        # region base ----------------------------------------------------------------------------------------------------
        # Calculate the amplitude between EMA and TEMA
        base_mamplitude = None
        base_mamplitude_temp = round(abs(base_ema - base_tema), precision)
        base_mamplitude_temp = round((base_mamplitude_temp / price) * 100, precision) if price != 0 else 0
        if base_mamplitude_temp > self.base_mamplitude:
            self.base_mamplitude = base_mamplitude_temp

        # Calculate the amplitude between current price and previous cross price
        base_pamplitude = None
        if self.base_cross_price:
            base_pamplitude_temp = round(abs(price - self.base_cross_price), precision)
            base_pamplitude_temp = round((base_pamplitude_temp / price) * 100, precision) if price != 0 else 0
            if base_pamplitude_temp > self.base_pamplitude:
                self.base_pamplitude = base_pamplitude_temp
        base_mamplitude = self.base_mamplitude
        base_pamplitude = self.base_pamplitude

        

        # Real direction changes
        base_direction_change = 0
        base_cross_price = None
        if base_tema < base_ema:
            if self.base_direction == 1:  # If last cross was up
                base_direction_change = -1
                base_cross_price = price
                pl = base_cross_price - self.base_cross_price if self.base_cross_price else 0
                self.base_cross_price = price
            self.base_direction = -1
        elif base_tema > base_ema:
            if self.base_direction == -1:  # If last cross was down
                base_direction_change = 1
                base_cross_price = price
                pl = base_cross_price - self.base_cross_price if self.base_cross_price else 0
                self.base_cross_price = price
            self.base_direction = 1

        # Conditional direction change for take to happen
        base_take_cross_price = base_take_cross_price_up = base_take_cross_price_dn = None
        base_signal = None
        if base_direction_change > 0:   # up
            if price > base_ema or price > base_tema:
                base_signal = 1
        elif base_direction_change < 0: # dn
            if price < base_ema or price < base_tema:
                base_signal = -1

        base_mpamplitude = None
        if base_direction_change > 0:   # up
            if price > base_ema or price > base_tema:
                base_mpamplitude = abs(base_ema - price)
        elif base_direction_change < 0: # dn
            if price < base_ema or price < base_tema:
                base_mpamplitude = abs(base_ema - price)

         # every row, calculate the min max price
        if self.base_direction == -1:
            if price < self.base_min_price_temp:
                self.base_min_price_temp = price
        if base_direction_change == 1:
            self.base_min_price = self.base_min_price_temp
            self.base_min_price_temp = np.inf
        if self.base_direction == 1:
            if price > self.base_max_price_temp:
                self.base_max_price_temp = price
        if base_direction_change == -1:
            self.base_max_price = self.base_max_price_temp
            self.base_max_price_temp = -np.inf

        if base_direction_change:
            self.base_mamplitude = 0
            self.base_pamplitude = 0
        # endregion base

        # region peak -------------------------------------------------------------------------------------------------
        # Calculate price amplitude
        peak_pamplitude = None
        if self.peak_cross_price:
            peak_pamplitude_temp = abs((price - self.peak_cross_price) / self.peak_cross_price * 100)
            if abs(peak_pamplitude_temp) > abs(self.peak_pamplitude):
                self.peak_pamplitude = peak_pamplitude_temp

        # Time based movement tamplitude
        peak_tamplitude = None
        self.peak_tamplitude_calculator.add(timestamp, price)
        peak_tamplitude_temp = abs(self.peak_tamplitude_calculator.calc())
        if abs(peak_tamplitude_temp) > abs(self.peak_tamplitude):
            self.peak_tamplitude = peak_tamplitude_temp
        peak_pamplitude = self.peak_pamplitude
        peak_tamplitude = self.peak_tamplitude

        # Real direction changes
        peak_direction_change = 0
        peak_cross_price = None
        if peak_tema < peak_ema:
            if self.peak_direction == 1:  # If last cross was up
                peak_direction_change = -1
                self.peak_cross_price = price
                peak_cross_price = price
            self.peak_direction = -1
        elif peak_tema > peak_ema:
            if self.peak_direction == -1:  # If last cross was down
                peak_direction_change = 1
                self.peak_cross_price = price
                peak_cross_price = price
            self.peak_direction = 1

        # Conditional direction change for take to happen
        peak_signal = None
        if peak_direction_change > 0:  # up
            peak_signal = 1
        elif peak_direction_change < 0:  # down
            peak_signal = -1

        # Reset amplitudes after processing
        if peak_direction_change:
            self.peak_pamplitude = 0
            self.peak_tamplitude_calculator.clear()
            self.peak_tamplitude = 0

        # --------------------------------------------------------------------------------------------------------------------------------------------------
        # Extreme peak detection
        if self.peak_direction > 0:  # if we are going up
            distant_price = price - self.peak_follower_distance
            if self.peak_follower_up is None or distant_price > self.peak_follower_up:
                self.peak_follower_up = distant_price

        elif self.peak_direction < 0:  # if we are going down
            distant_price = price + self.peak_follower_distance
            if self.peak_follower_dn is None or distant_price < self.peak_follower_dn:
                self.peak_follower_dn = distant_price

        if peak_direction_change:
            self.peak_follower_up = None
            self.peak_follower_dn = None


        # # Follow the price until it crosses
        # xtpk_signal = None
        # if not xtpk_signal:
        #     if self.peak_extreme_follower_up:
        #         if price < self.peak_extreme_follower_up:
        #             xtpk_signal = 1
        #     if self.peak_extreme_follower_dn:
        #         if price > self.peak_extreme_follower_dn:
        #             xtpk_signal = -1


        #     self.peak_extreme_follower_up = None
        #     self.peak_extreme_follower_dn = None
        # endregion peak
       
        # region asperity ------------------------------------------------------------------------------------------------
        # Real direction changes
        aspr_direction_change = 0
        if aspr_tema < aspr_ema:
            if self.aspr_direction == 1:  # If last cross was up
                aspr_direction_change = -1
                self.aspr_cross_price = price
            self.aspr_direction = -1
        elif aspr_tema > aspr_ema:
            if self.aspr_direction == -1:  # If last cross was down
                aspr_direction_change = 1
                self.aspr_cross_price = price
            self.aspr_direction = 1

        # Every row, calculate the min max price
        if self.aspr_direction == -1:
            if price < self.aspr_min_price_temp:
                self.aspr_min_price_temp = price
        if aspr_direction_change == 1:
            self.aspr_min_price_previous = self.aspr_min_price
            self.aspr_min_price = self.aspr_min_price_temp
            self.aspr_min_price_temp = np.inf
        if self.aspr_direction == 1:
            if price > self.aspr_max_price_temp:
                self.aspr_max_price_temp = price
        if aspr_direction_change == -1:
            self.aspr_max_price_previous = self.aspr_max_price
            self.aspr_max_price = self.aspr_max_price_temp
            self.aspr_max_price_temp = -np.inf

        # every row, calculate the min price of all prices since last cross down
        aspr_sideways = None
        aspr_min_amplitude = aspr_max_amplitude = aspr_mai_amplitude = None
        if self.aspr_min_price and self.aspr_min_price_previous and self.aspr_max_price and self.aspr_max_price_previous:
            aspr_min_amplitude = round((amp_raw := abs(self.aspr_min_price - self.aspr_min_price_previous)) / price * 100, precision) if price != 0 else 0
            aspr_max_amplitude = round((amp_raw := abs(self.aspr_max_price - self.aspr_max_price_previous)) / price * 100, precision) if price != 0 else 0
            aspr_mai_amplitude = (amptemp1 := round((abs(self.aspr_max_price - price) / price) * 100, precision) if price != 0 else 0) + (amptemp2 := round((abs(self.aspr_min_price - price) / price) * 100, precision) if price != 0 else 0) / 2
        # endregion asperity


        temp_value_1 = base_mpamplitude # aspr_mai_amplitude
        temp_value_2 = aspr_min_amplitude
        temp_value_3 = aspr_max_amplitude
        temp_value_4 = aspr_sideways

        return_dict = {
            'timestamp': timestamp,
            'price': price,

            'base_signal': base_signal,
            'base_ema': base_ema,
            'base_tema': base_tema,
            'base_cross_price': base_cross_price,
            'base_direction': self.base_direction,
            'base_mamplitude': base_mamplitude,
            'base_pamplitude': base_pamplitude,
            'base_min_price': self.base_min_price,
            'base_max_price': self.base_max_price,

            'peak_signal': peak_signal,
            'peak_cross_price': peak_cross_price,
            'peak_direction': self.peak_direction,
            'peak_pamplitude': peak_pamplitude,
            'peak_tamplitude': peak_tamplitude,
            'peak_follower_up': self.peak_follower_up,
            'peak_follower_dn': self.peak_follower_dn,

            'aspr_min_price': self.aspr_min_price,
            'aspr_max_price': self.aspr_max_price,
            'temp_value_1': temp_value_1,
            'temp_value_2': temp_value_2,
            'temp_value_3': temp_value_3,
            'temp_value_4': temp_value_4,
        }

        return return_dict


