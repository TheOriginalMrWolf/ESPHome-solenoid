# Overview

# This component is intended to simplify driving the main 3 different types
# of sprinkler solenoids used in irrigation systems.

# Interestingly enough, despite the nomenclature, all three main types of
# irrigation solenoid can usually be successfully driven with a simple
# 9-12v DC supply powering an h-bridge, modulating the output in certain specific ways.

# By using this componenent you can build a generic solution that handles any kind of laod.

# Pro:  h-bridges are generally both incredibly cheap and incredibly robust.
# Con:  by default uses two GPIOs per solenoid, though it's possible to wire the ESP &
#       h-bridge (or alternative circuit) so that you only use one GPIO per solenoid -
#       but only for AC or DC solenoids.  2 GPIOs are mandatory for DC Latching.

# The solendoid switch component exposes a solenoid platform (for a switch integration)
# which in turn drives a 'float' mode output component.

# This can be used by, for instance, the Sprinkler integration.  The Sprinkler component
# drives switches which implement the solenoid platform, which in turn drives physical
# float-type outputs.

# A single solenoid switch is therefore intended to drive an h-bridge using at least 2 float
# GPIOs per solenoid output.

# Configurations using only a FET (ie low-side switch), single GPIO, and second connection
# tied to ground are also possible (& planned for a future release).

# Background:

# The 3 main types of irrigation solenoid (not counting generic 'ac/dc' units), and their
# requirements, are:

#   DC Latching
#       Generally used by low-power battery / solar powered controllers.

#       Varies by solenoid but generally requires a 6-12V pulse, usually about
#       20-30ms, to either turn on or off.  9V DC power supplies are cheap and usually
#       work well (a lot of controllers are powered by either a 9V battery or 4 to 6 of
#       1.5V batteries in series (ie 6-9V)).

#       On receiving the pulse the solenoid will physically either extend or retract and
#       then latch into this position with no further power required (keeping the solenoid
#       energised wastes energy and can in fact cause it to overheat).

#       Polarity of the pulse (ie direction of the flow of current through the solenoid)
#       determines whether the valve ends up being set to 'on' or 'off' position (hence
#       requiring an h-bridge).

#   AC
#       Usually 24V AC, 50 or 60Hz depending on location.  Generally used by mains powered
#       controllers.  Solendoid is energised (& water flows) for as long as power is supplied.
#       Normally the approach is to use a 24V AC transformer which is usually controlled with
#       a relay, triac, or similar.
#       Depending on manufacture, can overheat if DC power applied for too long.

#       Alternative drive strategy implemented by this component -
#           * drive with 9-12V DC
#           * use an h-bridge (driven by either 1 or 2 GPIOs)
#           * PWM at up to 100% duty cycle for a second or so to pull in the plunger
#               - the 'energise' phase
#               - depends on the solenoid being used
#               - AC solenoids are totally happy with short bursts of DC
#           * Drop PWM duty down to 50-70% to keep plunger retracted
#               - the 'hold' phase
#               - depends on the solenoid being used
#               - uses less power & guarantees that the coil won't overheat
#           * When a solenoid is turned on, alternate between 'energise' and 'hold' for
#             several seconds to help ensure the plunger retracts fully, and then stay in
#             'hold' mode.

#       During PWM, on the 'off' switch cycle, configure the h-bridge to short the solenoid
#       terminals.  This allows the coil to retain more energy as the magnetic field collapses,
#       reducing or eliminiting buzz and using less energy overall.


#   DC
#       Usually in the 12V DC range.  Generally used by mains powered controllers.
#       Solenoid is energised (& water flows) for as long as power is supplied.
#       Normally the approach is to use a 9-12Vdc power supply, and switch solenoids
#       with either a relay, transistors, or FETs.

#       Alternative drive strategy implemented by this component -
#           * drive with 9-12V DC
#           * use an h-bridge (driven by either 1 or 2 GPIOs)
#           * Energise with 100% power (polarity irrelevant) for, say, 5 secs
#           * Hold with PWN at, say, 50-70% (uses less power)

#   The advantage of AC & DC solenoids is that, once power is removed, you're pretty much
#   guaranteed that the plunger will extend and water will stop flowing.  DC latching solenoids
#   are usually pretty reliable - however can remain in the 'on' position if the controller
#   lacks the power to drive the solenoid properly (ie low battery situation).

#   This works like:
#       * GPIO - platform for switch
#       * H Bridge - config plus driving an output

#   Tricky bit with H Bridges
#       some are 2 pin & some are 3 pin
#       generally you have 'forward', 'back', and 'stop'
#       'stop' can be implemented two ways:
#           1 - short the terminals together (this slows the magnetic field collapse, but causes motors to 'hard brake'). Often implemented by switching both to ground
#           2 - go to 'high z' which isolates the terminals (though might still be subject to body-diode clamping), causing fast magnetic field collaps & letting motors 'coast'
#
#       2-pin H-bridges normally differentiate between coast & brake by setting both pins either high or low
#       3-pin H-bridges normally support power/coast through the enable pin, and brake through a specific setting of A & B (possibly also including a particular state for ENABLE)
#
#       For motors, when doing speed control, you want the PWM to run in power/coast cycle.
#       For AC & DC solenoids however you actually want the PWM to be a power/brake cycle to minimise buzz / energy loss / heat
#       Don't really care for latching DC
#
#       So, for PWM control of solenoids you want to know:
#           - which pin to modulate
#           - what state to hold the other pin(s)
#           - if the PWM value needs to be inverted (due to the pin state requried for 'brake' mode)

#       For 2- & 3-pin H-bridge:
#           RUN:
#           - PIN A is modulated
#           - PIN B is held at BRAKE (this sustains the magnetic field for longer, reducing buzz & power dissipation)
#           - If BRAKE is HIGH, then PIN A power is inverted (because HH = 'off')
#           STOP:
#           - PIN B is dropped to COAST
#           - PIN A same as B

#       If 3-pin H-bridge:
#           ENABLE is held HIGH for ON, and set LOW for OFF


import esphome.codegen as cg
import esphome.config_validation as cv

from esphome.components import switch, output
from .. import solenoid_ns

from esphome.const import (
    CONF_OUTPUT_ID,
    CONF_INTERLOCK,
    CONF_PIN_A,
    CONF_PIN_B,
    CONF_INVERTED,
)

SolenoidSwitch = solenoid_ns.class_("SolenoidSwitch", switch.Switch, cg.Component)

SolenoidType = solenoid_ns.enum("SolenoidType")
SOLENOID_TYPE_OPTIONS = {
    "DC_LATCHING": SolenoidType.SOLENOID_TYPE_DC_LATCHING,
    "AC": SolenoidType.SOLENOID_TYPE_AC,
    "DC": SolenoidType.SOLENOID_TYPE_DC,
}

CONF_ENERGISE_DURATION_MS = "energise_duration_ms"
CONF_ENERGISE_POWER_PERCENT = "energise_power_percent"
CONF_HOLD_POWER_PERCENT = "hold_power_percent"
CONF_SOLENOID_TYPE = "solenoid_type"
CONF_INTERLOCK_WAIT_TIME = "interlock_wait_time"
CONF_BRAKE_IS_HIGH = "brake_is_high"
CONF_BRIDGE_ENABLE_PIN = "h_bridge_enable_pin"
CONF_DC_LATCH_REDO_COUNT = "dc_latch_redo_count"
CONF_DC_LATCH_REDO_INTERVAL_MS = "dc_latch_redo_interval_ms"
CONF_USING_HALF_BRIDGE = "using_half_bridge"

# Explicitly asking for either PIN_B or USING_HALF_BRIDGE to be defined so as to avoid accidental
# misconfiguration, plus makes the logic a teensy bit less convoluted.

def validate_dc_latching_solenoid(config):
    if config[CONF_SOLENOID_TYPE] == "DC_LATCHING":
        if config[CONF_USING_HALF_BRIDGE] == True:
            raise cv.Invalid("DC Latching Solenoid can't use a half-bridge as it requires a full h-bridge in order to reverse pulse polarity.")
        if CONF_PIN_B not in config:
            raise cv.Invalid("DC Latching Solenoid requires " + CONF_PIN_B + " to be defined.")
    return config

def validate_pin_b_and_half_bridge_combo(config):
    if CONF_USING_HALF_BRIDGE in config and config[CONF_USING_HALF_BRIDGE] == True and CONF_PIN_B in config:
        raise cv.Invalid("Cannot be using a half-bridge AND have " + CONF_PIN_B + " defined. Choose one or the other please.")
    if CONF_USING_HALF_BRIDGE in config and config[CONF_USING_HALF_BRIDGE] == False and CONF_PIN_B not in config:
        raise cv.Invalid("Must be either using a half-bridge OR have " + CONF_PIN_B + " defined. Choose only one of the two please.")
    return config


CONFIG_SCHEMA = cv.All(
    switch.switch_schema(SolenoidSwitch)
    .extend(
        {
            cv.GenerateID(CONF_OUTPUT_ID): cv.declare_id(SolenoidSwitch),
            cv.Required(CONF_PIN_A): cv.use_id(output.FloatOutput),
            cv.Optional(CONF_PIN_B): cv.use_id(output.BinaryOutput),
            cv.Optional(CONF_BRIDGE_ENABLE_PIN): cv.use_id(output.BinaryOutput),
            cv.Required(CONF_ENERGISE_DURATION_MS): cv.int_range(min=10, max=3000),
            cv.Optional(CONF_DC_LATCH_REDO_COUNT, default = 3): cv.int_range(min=1, max=5),
            cv.Optional(CONF_DC_LATCH_REDO_INTERVAL_MS, default=500): cv.int_range(min=500, max=3000),
            cv.Optional(CONF_ENERGISE_POWER_PERCENT, default = "95%"): cv.percentage,
            cv.Optional(CONF_HOLD_POWER_PERCENT, default = "55%"): cv.percentage,
            cv.Required(CONF_SOLENOID_TYPE): cv.enum(SOLENOID_TYPE_OPTIONS, upper=True),
            cv.Required(CONF_BRAKE_IS_HIGH): cv.boolean,
            cv.Optional(CONF_INVERTED, default=False): cv.boolean,
            cv.Optional(CONF_USING_HALF_BRIDGE, default = False): cv.boolean,
            cv.Optional(CONF_INTERLOCK): cv.ensure_list(cv.use_id(switch.Switch)),
            cv.Optional(CONF_INTERLOCK_WAIT_TIME, default="0ms"): cv.positive_time_period_milliseconds,
        }
    )
    .extend(cv.COMPONENT_SCHEMA),
    validate_dc_latching_solenoid,
    validate_pin_b_and_half_bridge_combo
)


async def to_code(config):
    solenoid_switch = await switch.new_switch(config)
    await cg.register_component(solenoid_switch, config)

    bridge_a_side_id = await cg.get_variable(config[CONF_PIN_A])
    cg.add(solenoid_switch.connect_a_pin(bridge_a_side_id))

    if CONF_PIN_B in config:
        bridge_b_side_id = await cg.get_variable(config[CONF_PIN_B])
        cg.add(solenoid_switch.connect_b_pin(bridge_b_side_id))

    if CONF_BRIDGE_ENABLE_PIN in config:
        bridge_enable_pin_id = await cg.get_variable(config[CONF_BRIDGE_ENABLE_PIN])
        cg.add(solenoid_switch.connect_enable_pin(bridge_enable_pin_id))

    cg.add(solenoid_switch.set_energise_duration_ms(config[CONF_ENERGISE_DURATION_MS]))
    cg.add(solenoid_switch.set_dc_latch_redo_count(config[CONF_DC_LATCH_REDO_COUNT]))
    cg.add(solenoid_switch.set_dc_latch_redo_interval(config[CONF_DC_LATCH_REDO_INTERVAL_MS]))
    cg.add(solenoid_switch.set_energise_power_percent(config[CONF_ENERGISE_POWER_PERCENT]))
    cg.add(solenoid_switch.set_hold_power_percent(config[CONF_HOLD_POWER_PERCENT]))
    cg.add(solenoid_switch.set_solenoid_type(config[CONF_SOLENOID_TYPE]))
    cg.add(solenoid_switch.set_brake(config[CONF_BRAKE_IS_HIGH]))
    cg.add(solenoid_switch.set_inverted(config[CONF_INVERTED]))
    # if CONF_USING_HALF_BRIDGE in config: - not necessary as it has a default value
    cg.add(solenoid_switch.set_half_bridge(config[CONF_USING_HALF_BRIDGE]))

    if CONF_INTERLOCK in config:
        interlock = []
        for it in config[CONF_INTERLOCK]:
            lock = await cg.get_variable(it)
            interlock.append(lock)
        cg.add(solenoid_switch.set_interlock(interlock))
        cg.add(solenoid_switch.set_interlock_wait_time(config[CONF_INTERLOCK_WAIT_TIME]))

