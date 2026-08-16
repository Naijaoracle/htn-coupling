#!/usr/bin/env julia

using DelimitedFiles
using openBF

length(ARGS) == 2 || error("usage: run_stage4_openbf.jl YAML RESULT_DIR")
yaml, result_dir = ARGS
started = time()
openBF.run_simulation(yaml; verbose=true, out_files=false,
                      save_stats=true, savedir=result_dir)
pressure = readdlm(joinpath(result_dir, "aortic_arch_I_P.last"))
all(isfinite, pressure) || error("openBF produced non-finite aortic pressure")
open(joinpath(result_dir, "bridge_wall_time_s.txt"), "w") do io
    println(io, time() - started)
end
