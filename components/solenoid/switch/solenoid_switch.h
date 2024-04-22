#pragma once

#include "esphome/core/component.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/output/float_output.h"
#include "esphome/components/output/binary_output.h"
#include "esphome/core/log.h"

#include <vector>

namespace esphome {
namespace solenoid {

enum SolenoidType { SOLENOID_TYPE_DC_LATCHING, SOLENOID_TYPE_AC, SOLENOID_TYPE_DC };

class SolenoidSwitch : public switch_::Switch, public Component {
 public:
  void connect_a_pin(output::FloatOutput *a_pin) { this->a_pin_float_ = a_pin; }
  void connect_b_pin(output::BinaryOutput *b_pin) { this->b_pin_binary_ = b_pin; }
  void connect_enable_pin(output::BinaryOutput *enable_pin) { this->enable_pin_binary_ = enable_pin; }
  void set_solenoid_type(SolenoidType solenoid_type) { this->solenoid_type_ = solenoid_type; }
  void set_brake(bool brake_is_high) { this->brake_is_high_ = brake_is_high; }
  void set_energise_duration_ms(uint16_t energise_duration_ms) { this->energise_duration_ms_ = energise_duration_ms; }
  void set_energise_power_percent(float energise_power_percent) { this->energise_power_percent_ = energise_power_percent; }
  void set_hold_power_percent(float hold_power_percent) { this->hold_power_percent_ = hold_power_percent; }
  void set_dc_latch_redo_count(uint8_t dc_latch_redo_count) { this->dc_latch_redo_count_ = dc_latch_redo_count; }
  void set_dc_latch_redo_interval(uint16_t dc_latch_redo_interval_ms) { this->dc_latch_redo_interval_ms_ = dc_latch_redo_interval_ms; }

  // float get_setup_priority() const override;
  float get_setup_priority() const override { return setup_priority::HARDWARE; }

  void setup() override;
  void dump_config() override;
  void set_interlock(const std::vector<Switch *> &interlock);
  void set_interlock_wait_time(uint32_t interlock_wait_time) { interlock_wait_time_ = interlock_wait_time; }

  void set_inverted(bool inverted) { inverted_ = inverted; }

 protected:
  output::FloatOutput *a_pin_float_{nullptr};
  output::BinaryOutput *b_pin_binary_{nullptr};
  output::BinaryOutput *enable_pin_binary_{nullptr};
  bool brake_is_high_{true};
  uint16_t energise_duration_ms_;
  float energise_power_percent_;
  float hold_power_percent_;

  uint8_t dc_latch_redo_count_;
  uint8_t dc_latch_redo_trigger_count = 0;
  uint16_t dc_latch_redo_interval_ms_;

  bool inverted_;

  std::vector<Switch *> interlock_;
  uint32_t interlock_wait_time_{0};

  SolenoidType solenoid_type_;

  void write_state(bool state) override;
  void control_ac_dc_solenoid(bool state);
  void control_dc_latching_solenoid(bool state);
};

}  // namespace solenoid
}  // namespace esphome
