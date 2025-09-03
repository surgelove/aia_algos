
from helper import *

class Decider:
    """
    Decider class that uses the Algo class to make decisions based on moving averages.
    
    Key Features:
    - Processes rows of data to calculate moving averages
    - Makes decisions based on calculated values
    """

    def __init__(self):
        self.base_mamplitude_threshold = 0.02 
        self.base_mamplitude_enough = False
        self.base_pamplitude_threshold = 0.03
        self.base_pamplitude_enough = False 

        self.peak_pamplitude_threshold = 0.04
        self.peak_pamplitude_enough = False
        self.peak_tamplitude_threshold = 0.02
        self.peak_tamplitude_enough = False 
        self.xtpk_found = False

        self.peak_extreme_distance = 0.0002

        self.aspr_xamplitude_threshold = 0.04
        self.aspr_sideways_count = 0
        self.xtpk_price_dn_following_crossed = False
        self.xtpk_price_up_following_crossed = False

    def decide(self, return_dict, say):
        # get take value from return_dict
        price = return_dict.get('price')

        decision = decision_up = decision_dn = decision_algo = message = None

        # region Base
        base_signal = return_dict.get('base_signal')
        base_cross_price = return_dict.get('base_cross_price')
        base_direction = return_dict.get('base_direction')
        base_mamplitude = return_dict.get('base_mamplitude')
        base_pamplitude = return_dict.get('base_pamplitude')
        base_min_price = return_dict.get('base_min_price')
        base_max_price = return_dict.get('base_max_price')

        base_signal_up = base_signal_dn = None
        if base_signal:
            if base_mamplitude >= self.base_mamplitude_threshold and base_pamplitude >= self.base_pamplitude_threshold:
                decision = base_signal
                decision_algo = 'base'
                if base_signal > 0:
                    base_signal_up = decision_up = price
                elif base_signal < 0:
                    base_signal_dn = decision_dn = price
                message = f'signal {updown(base_signal)} from algo {decision_algo} with enough amplitude'
                if say: say_nonblocking(message)
            else:
                decision = base_signal
                decision_algo = 'base'
                if base_signal > 0:
                    if base_max_price:
                        base_signal_up = decision_up = base_max_price + 0.0001
                elif base_signal < 0:
                    if base_min_price:
                        base_signal_dn = decision_dn = base_min_price - 0.0001
                message = f'signal {updown(base_signal)} from algo {decision_algo} without enough amplitude'
                if say: say_nonblocking(message)
        # endregion Base

        # region Peak
        peak_signal = return_dict.get('peak_signal')
        peak_cross_price = return_dict.get('peak_cross_price')
        peak_direction = return_dict.get('peak_direction')
        peak_pamplitude = return_dict.get('peak_pamplitude')
        peak_tamplitude = return_dict.get('peak_tamplitude')
        peak_follower_up = return_dict.get('peak_follower_up')
        peak_follower_dn = return_dict.get('peak_follower_dn')

        peak_signal_up = peak_signal_dn = None 
        if peak_signal:
            if peak_pamplitude >= self.peak_pamplitude_threshold and peak_tamplitude >= self.peak_tamplitude_threshold:
                print('peak signal')
                decision = peak_signal
                decision_algo = 'peak'
                if peak_signal > 0:
                    peak_signal_up = decision_up = price
                elif peak_signal < 0:
                    peak_signal_dn = decision_dn = price
                message = f'signal {updown(peak_signal)} from algo {decision_algo} with enough amplitude'
                print(message)
        
        # TODO: capture the very bottom peak, not the first one only
        xtpk_signal_up = xtpk_signal_dn = None
        if peak_pamplitude >= self.peak_pamplitude_threshold and peak_tamplitude >= self.peak_tamplitude_threshold:
            if not self.xtpk_found:
                if peak_follower_dn:
                    if price > peak_follower_dn:
                        print('peak follower down')
                        xtpk_signal_up = decision_up = price
                        self.xtpk_found = True
                if peak_follower_up:
                    if price < peak_follower_up:
                        print('peak follower up')
                        xtpk_signal_dn = decision_dn = price
                        self.xtpk_found = True
        else:
            self.xtpk_found = False
        # endregion Peak
            

        return_dict.update({
            'base_signal_up': base_signal_up,
            'base_signal_dn': base_signal_dn,
            'base_mamplitude_threshold': self.base_mamplitude_threshold,
            'base_pamplitude_threshold': self.base_pamplitude_threshold,

            'peak_signal_up': peak_signal_up,
            'peak_signal_dn': peak_signal_dn,
            'peak_pamplitude_threshold': self.peak_pamplitude_threshold,
            'peak_tamplitude_threshold': self.peak_tamplitude_threshold,
            'xtpk_signal_up': xtpk_signal_up,
            'xtpk_signal_dn': xtpk_signal_dn,

            'decision': decision,
            'decision_algo': decision_algo,
            'message': message,
            'decision_up': decision_up,
            'decision_dn': decision_dn,
        })

        return return_dict
