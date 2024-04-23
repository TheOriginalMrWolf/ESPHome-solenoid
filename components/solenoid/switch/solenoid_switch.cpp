#include "solenoid_switch.h"

namespace esphome {
namespace solenoid {

static const char *const TAG = "switch.solenoid";

// float SolenoidSwitch::get_setup_priority() const { return setup_priority::HARDWARE; }

void SolenoidSwitch::setup() {
  ESP_LOGCONFIG(TAG, "Setting up SOLENOID Switch '%s'...", this->name_.c_str());

  bool initial_state = this->get_initial_state_with_restore_mode().value_or(false);

  // write state before setup
  // if (initial_state) {
  //   this->turn_on();
  // } else {
  //   this->turn_off();
  // }
  // this->pin_->setup();
  // write after setup again for other IOs
  if (initial_state) {
    this->turn_on();
  } else {
    this->turn_off();
  }
}

void SolenoidSwitch::dump_config() {
  LOG_SWITCH("", "SOLENOID Switch", this);

  switch (this->solenoid_type_) {
    case SOLENOID_TYPE_AC:
      ESP_LOGCONFIG(TAG, "Solenoid type: AC");
      break;
    case SOLENOID_TYPE_DC:
      ESP_LOGCONFIG(TAG, "Solenoid type: DC");
      break;
    case SOLENOID_TYPE_DC_LATCHING:
      ESP_LOGCONFIG(TAG, "Solenoid type: DC Latching");
      break;
    default:
      ESP_LOGE(TAG, "Invalid solenoid_type selection!");
      break;
  }

  ESP_LOGCONFIG(TAG, "Enable pin %sdefined", this->enable_pin_binary_ ? "" : "not ");
  ESP_LOGCONFIG(TAG, "Brake is %s", this->brake_is_high_ ? "high" : "low");
  ESP_LOGCONFIG(TAG, "Energise duration: %ums", this->energise_duration_ms_);
  ESP_LOGCONFIG(TAG, "Energise power: %f", this->energise_power_percent_);
  ESP_LOGCONFIG(TAG, "Hold power: %f", this->hold_power_percent_);

  // LOG_FLOAT_OUTPUT(this->a_pin_float_);
  if (!this->interlock_.empty()) {
    ESP_LOGCONFIG(TAG, "  Interlocks:");
    for (auto *lock : this->interlock_) {
      if (lock == this)
        continue;
      ESP_LOGCONFIG(TAG, "    %s", lock->get_name().c_str());
    }
  }
}

void SolenoidSwitch::write_state(bool state) {
  if (state != this->inverted_) {
    // Turning ON, check interlocking

    bool found = false;
    for (auto *lock : this->interlock_) {
      if (lock == this)
        continue;

      if (lock->state) {
        lock->turn_off();
        found = true;
      }
    }
    if (found && this->interlock_wait_time_ != 0) {
      this->set_timeout("interlock", this->interlock_wait_time_, [this, state] {
        // Don't write directly, call the function again
        // (some other switch may have changed state while we were waiting)
        this->write_state(state);
      });
      return;
    }
  } else if (this->interlock_wait_time_ != 0) {
    // If we are switched off during the interlock wait time, cancel any pending re-activations
    this->cancel_timeout("interlock");
  }

  switch (this->solenoid_type_) {
    case SOLENOID_TYPE_AC:
    case SOLENOID_TYPE_DC:
      control_ac_dc_solenoid(state);
      break;
    case SOLENOID_TYPE_DC_LATCHING:
      control_dc_latching_solenoid(state);
      break;
    default:
      ESP_LOGE(TAG, "Invalid solenoid_type selection!");
      break;
  }

  this->publish_state(state);
}

void SolenoidSwitch::set_interlock(const std::vector<Switch *> &interlock) { this->interlock_ = interlock; }

void SolenoidSwitch::control_ac_dc_solenoid(bool state) {
  this->cancel_timeout("start_hold");

  if (this->inverted_) state = !state;

  // Turn On
  if (state) {
    this->b_pin_binary_->set_state(this->brake_is_high_);                                                                       // set the brake pin
    this->a_pin_float_->set_level(this->brake_is_high_ ? 1.0 - this->energise_power_percent_ : this->energise_power_percent_);  // set the 'drive' pin - inverting waveform as necessary

    if (this->enable_pin_binary_) {  // aaaand.. enable... if it has one
      this->enable_pin_binary_->set_state(state);
    }

    this->set_timeout("start_hold",
        this->energise_duration_ms_,
        [this]() {  // set hold power level after timeout - inverting waveform as necessary
          this->a_pin_float_->set_level(this->brake_is_high_ ? 1.0 - this->hold_power_percent_ : this->hold_power_percent_);
        });
    return;
  }

  // Turn Off
  bool off_level = !this->brake_is_high_;
  if (this->enable_pin_binary_) {
    this->enable_pin_binary_->set_state(state);
  }
  this->b_pin_binary_->set_state(off_level);
  this->a_pin_float_->set_level(off_level);
}

void SolenoidSwitch::control_dc_latching_solenoid(bool state) {
  this->cancel_timeout("latch_pulse");
  if (this->inverted_) state = !state;

  // when de-energising the solenoid we want to sustain the magnetic field to minimise chance of unhooking the magnetic
  // latch
  bool dc_latch_on_level_ = !this->brake_is_high_;
  bool dc_latch_off_level_ = !dc_latch_on_level_;

  // kick the solenoid to on or off position
  ESP_LOGD("DC-LATCH", "Turning DC solenoid %s. On level: %f, off level %f", state ? "on" : "off", dc_latch_on_level_, dc_latch_off_level_);

  if (state) {
    this->a_pin_float_->set_level(dc_latch_on_level_);
    this->b_pin_binary_->set_state(dc_latch_off_level_);
  } else {
    this->a_pin_float_->set_level(dc_latch_off_level_);
    this->b_pin_binary_->set_state(dc_latch_on_level_);
  }
  if (this->enable_pin_binary_) {
    this->enable_pin_binary_->turn_on();
  }

  // then de-energise again after timeout
  this->set_timeout("latch_pulse", this->energise_duration_ms_, [this, dc_latch_off_level_]() {
    this->a_pin_float_->set_level(dc_latch_off_level_);
    this->b_pin_binary_->set_state(dc_latch_off_level_);

    // DC latching can be unreliable, so kick the solenoid a few times
    // Schedule the redo
    if (this->dc_latch_redo_trigger_count++ < this->dc_latch_redo_count_) {
      this->set_timeout("latch_pulse", this->dc_latch_redo_interval_ms_, [this]() { this->control_dc_latching_solenoid(this->state); });
      return;
    }

    // no more redos, so reset the counter and schedule disable for 3-pin
    this->dc_latch_redo_trigger_count = 0;

    // NOTE:
    // Interesting issue.  I wanted to revert to 'resting' state from 'off' state.  In this scenario the 'off' state is the h-bridge's
    // 'brake' mode - ie the motor outputs are shorted.  This is great for DC Latching solenoids as it allows the field to collapse a
    // little slower, thereby reducing the risk of kicking the plunger away from the retaining magnet.
    // The 'resting' state is the bridge's 'high-z' (ie 'coast') mode - in theory requiring a tiny bit less energy and also isolating
    // the driver a little more from external influence.
    // unfortunately, at least for 2-pin h-bridges, we can't switch both outputs to resting level at exactly the same time.
    // This delta in turn unfortunately causes the solenoid to give a kick which is sometimes enough to get it to toggle.
    // Soooo... only doing this for 3-pin right now.
    if (this->enable_pin_binary_) {
      this->set_timeout(
        "latch_pulse",
        1000,
        [this]() {
          this->enable_pin_binary_->turn_off();
          // once enable is off then any timing delta doesn't matter... in theory...
          bool resting_state = !this->brake_is_high_;
          this->a_pin_float_->set_level(resting_state);
          this->b_pin_binary_->set_state(resting_state);
      });
    }
  });
}

}  // namespace solenoid
}  // namespace esphome
