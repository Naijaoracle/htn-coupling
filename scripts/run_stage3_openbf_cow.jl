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
model_dir = joinpath(checkout, "models", "alastruey2007")
yaml = joinpath(model_dir, "circle_of_willis.yaml")
isfile(yaml) || error("Circle-of-Willis configuration not found at $yaml")

result_dir = joinpath(PROJECT_ROOT, "results", "stage3", "openbf_circle_of_willis")
mkpath(result_dir)
openBF.run_simulation(yaml; verbose=true, out_files=false, save_stats=true, savedir=result_dir)

sites = ["10-L-ext-carotid", "18-L-int-carotidII", "13-R-ext-carotid", "21-R-int-carotidII"]
summary = Dict{String, Any}(
    "model" => "circle_of_willis",
    "openbf_revision" => HTNCoupling.OPENBF_REVISION,
)
for site in sites
    pressure_file = joinpath(result_dir, "$(site)_P.last")
    flow_file = joinpath(result_dir, "$(site)_Q.last")
    isfile(pressure_file) || error("Expected pressure output not found: $pressure_file")
    isfile(flow_file) || error("Expected flow output not found: $flow_file")
    pressure = readdlm(pressure_file)[:, end]
    flow = readdlm(flow_file)[:, end]
    summary[site] = Dict(
        "pressure_min_pa" => minimum(pressure),
        "pressure_max_pa" => maximum(pressure),
        "pressure_mean_pa" => mean(pressure),
        "flow_min_m3_s" => minimum(flow),
        "flow_max_m3_s" => maximum(flow),
        "flow_mean_m3_s" => mean(flow),
    )
end
open(joinpath(result_dir, "baseline_summary.toml"), "w") do io
    TOML.print(io, summary)
end
println(summary)
