#!/usr/bin/env julia

using DelimitedFiles
using HTNCoupling
using openBF
using Statistics
using TOML

const PROJECT_ROOT = normpath(joinpath(@__DIR__, ".."))
const LOCAL_REPOS = joinpath(PROJECT_ROOT, "config", "repos.local.toml")

function openbf_checkout()
    if isfile(LOCAL_REPOS)
        return TOML.parsefile(LOCAL_REPOS)["openbf"]["path"]
    end
    return normpath(joinpath(PROJECT_ROOT, "..", "openBF"))
end

checkout = openbf_checkout()
model_dir = joinpath(checkout, "models", "boileau2015", "adan56")
yaml = joinpath(model_dir, "adan56.yaml")
isfile(yaml) || error("adan56 configuration not found at $yaml")

result_dir = joinpath(PROJECT_ROOT, "results", "stage0", "openbf_adan56")
mkpath(result_dir)
openBF.run_simulation(yaml; verbose=true, out_files=false, save_stats=true, savedir=result_dir)

pressure_file = joinpath(result_dir, "aortic_arch_I_P.last")
isfile(pressure_file) || error("Expected pressure output not found: $pressure_file")
pressure = readdlm(pressure_file)
size(pressure, 2) == 6 || error("Unexpected pressure output shape: $(size(pressure))")

summary = Dict(
    "model" => "adan56",
    "openbf_revision" => HTNCoupling.OPENBF_REVISION,
    "pressure_file" => pressure_file,
    "samples" => size(pressure, 1),
    "inlet_pressure_min_pa" => minimum(pressure[:, 2]),
    "inlet_pressure_max_pa" => maximum(pressure[:, 2]),
    "inlet_pressure_mean_pa" => mean(pressure[:, 2]),
)
open(joinpath(result_dir, "baseline_summary.toml"), "w") do io
    TOML.print(io, summary)
end
println(summary)
