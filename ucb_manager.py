import math
import random
import logging

logger = logging.getLogger("UCB_Manager")

class UCBManager:
    def __init__(self, arms=None):
        if arms is None:
            self.arms = [0.1, 0.3, 0.5, 0.7, 0.9] # Available Gamma Values
        else:
            self.arms = arms
            
        self.counts = {arm: 0 for arm in self.arms}  # Number of times each arm was selected
        self.values = {arm: 0.0 for arm in self.arms} # Average reward for each arm
        self.total_counts = 0
        
        # Initialize with a random arm to start
        self.current_arm = random.choice(self.arms)
        self.last_arm = self.current_arm

    def select_arm(self):
        """
        Selects the next arm (Gamma) using the UCB1 algorithm.
        """
        # 1. Ensure every arm is played at least once
        for arm in self.arms:
            if self.counts[arm] == 0:
                self.current_arm = arm
                logger.info(f"[UCB] Cold Start: Trying Gamma={arm}")
                return arm

        # 2. UCB1 Logic
        best_arm = None
        max_ucb = -1.0
        
        for arm in self.arms:
            average_reward = self.values[arm]
            exploration_bonus = math.sqrt((2 * math.log(self.total_counts)) / self.counts[arm])
            ucb_score = average_reward + exploration_bonus
            
            if ucb_score > max_ucb:
                max_ucb = ucb_score
                best_arm = arm
        
        self.last_arm = self.current_arm # Store previous for reward attribution
        self.current_arm = best_arm
        logger.info(f"[UCB] Selected Gamma={best_arm} (Score={max_ucb:.4f})")
        return best_arm

    def update(self, reward):
        """
        Updates the Q-value (Average Reward) for the *last used* arm using the received reward.
        """
        arm = self.current_arm # The arm that just generated this reward
        
        self.counts[arm] += 1
        self.total_counts += 1
        
        # New Average = Old Average + (New Reward - Old Average) / N
        n = self.counts[arm]
        old_value = self.values[arm]
        new_value = old_value + (reward - old_value) / n
        
        self.values[arm] = new_value
        
        logger.info(f"[UCB] Updated Gamma={arm} | Reward={reward:.4f} | New Avg={new_value:.4f} | Count={n}")
