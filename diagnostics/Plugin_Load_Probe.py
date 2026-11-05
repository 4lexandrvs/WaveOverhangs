# /// script
# [tool.orcaslicer.plugin]
# name = "Wave Overhangs Load Probe"
# description = "Minimal diagnostic: verifies Python plugin import, package registration, capability load and manual execution."
# author = "WaveOverhangs contributors"
# version = "0.1.0"
# ///

import orca

print("[WAVE_OVERHANGS_LOAD_PROBE] module imported")


class WaveOverhangsLoadProbe(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Wave Overhangs Load Probe"

    def on_load(self):
        print("[WAVE_OVERHANGS_LOAD_PROBE] capability on_load called")

    def on_unload(self):
        print("[WAVE_OVERHANGS_LOAD_PROBE] capability on_unload called")

    def execute(self):
        print("[WAVE_OVERHANGS_LOAD_PROBE] execute called")
        return orca.ExecutionResult.success(
            "Wave Overhangs diagnostic succeeded: the module loaded, "
            "the capability was registered, and execute() was called."
        )


@orca.plugin
class WaveOverhangsLoadProbePackage(orca.base):
    def register_capabilities(self):
        print("[WAVE_OVERHANGS_LOAD_PROBE] register_capabilities called")
        orca.register_capability(WaveOverhangsLoadProbe)
        print("[WAVE_OVERHANGS_LOAD_PROBE] capability registration requested")
