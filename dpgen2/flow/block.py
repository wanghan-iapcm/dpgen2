from dflow import (
    InputParameter,
    OutputParameter,
    Inputs,
    InputArtifact,
    Outputs,
    OutputArtifact,
    Workflow,
    Step,
    Steps,
    upload_artifact,
    download_artifact,
    argo_range,
    argo_len,
    argo_sequence,
)
from dflow.python import(
    PythonOPTemplate,
    OP,
    OPIO,
    OPIOSign,
    Artifact,
    Slices,
)

from typing import Set, List
from pathlib import Path

def block_cl(
        name : str,
        prep_run_dp_train_op : OP,
        prep_run_lmp_op : OP,
        select_confs_op : OP,
        prep_run_fp_op : OP,
        collect_data_op : OP,
):
    block_steps = Steps(
        name = name,
        inputs = Inputs(
            parameters={
                "type_map" : InputParameter(),
                "numb_models": InputParameter(type=int),
                "template_script" : InputParameter(),
                "lmp_task_grps" : InputParameter(),
                "conf_selector" : InputParameter(),
                "conf_filters" : InputParameter(),
                "fp_inputs" : InputParameter(),
            },
            artifacts={
                "init_models" : InputArtifact(),
                "init_data" : InputArtifact(),
                "iter_data" : InputArtifact(),
            },
        ),
        outputs=Outputs(
            parameters={
                "exploration_report": OutputParameter(),
            },
            artifacts={
                "models": OutputArtifact(),
                "iter_data" : OutputArtifact(),
            },
        ),
    )

    prep_run_dp_train = Step(
        name + '-prep-run-dp-train',
        template = prep_run_dp_train_op,
        parameters={
            "numb_models": block_steps.inputs.parameters['numb_models'],
            "template_script": block_steps.inputs.parameters['template_script'],
        },
        artifacts={
            "init_models" : block_steps.inputs.artifacts['init_models'],
            "init_data" : block_steps.inputs.artifacts['init_data'],
            "iter_data" : block_steps.inputs.artifacts['iter_data'],
        },
    )
    block_steps.add(prep_run_dp_train)
        
    prep_run_lmp = Step(
        name = name + '-prep-run-lmp',
        template = prep_run_lmp_op,
        parameters={
            "lmp_task_grps": block_steps.inputs.parameters['lmp_task_grps'],
        },
        artifacts={
            "models" : prep_run_dp_train.outputs.artifacts['models'],
        },
    )
    block_steps.add(prep_run_lmp)
        
    select_confs = Step(
        name = name + '-select-confs',
        template=PythonOPTemplate(
            select_confs_op,
            image="dflow:v1.0",
            output_artifact_archive={
                "confs": None
            },
            python_packages = "..//dpgen2",
        ),
        parameters={
            "conf_selector": block_steps.inputs.parameters['conf_selector'],
            "conf_filters": block_steps.inputs.parameters['conf_filters'],
            "type_map": block_steps.inputs.parameters['type_map'],
            "traj_fmt": 'lammps/dump',
        },
        artifacts={
            "trajs" : prep_run_lmp.outputs.artifacts['trajs'],
            "model_devis" : prep_run_lmp.outputs.artifacts['model_devis'],
        },
    )
    block_steps.add(select_confs)
        
    prep_run_fp = Step(
        name = name + '-prep-run-fp',
        template = prep_run_fp_op,
        parameters={
            "inputs": block_steps.inputs.parameters['fp_inputs'],            
        },
        artifacts={
            "confs" : select_confs.outputs.artifacts['confs'],
        },
    )
    block_steps.add(prep_run_fp)

    collect_data = Step(
        name = name + '-collect-data',
        template=PythonOPTemplate(
            collect_data_op,
            image="dflow:v1.0",
            output_artifact_archive={
                "iter_data": None
            },
            python_packages = "..//dpgen2",
        ),
        parameters={
            "name": name,
        },
        artifacts={
            "iter_data" : block_steps.inputs.artifacts['iter_data'],
            "labeled_data" : prep_run_fp.outputs.artifacts['labeled_data'],
        },
    )
    block_steps.add(collect_data)

    block_steps.outputs.parameters["exploration_report"].value_from_parameter = \
        select_confs.outputs.parameters["report"]
    block_steps.outputs.artifacts["models"]._from = \
        prep_run_dp_train.outputs.artifacts["models"]
    block_steps.outputs.artifacts["iter_data"]._from = \
        collect_data.outputs.artifacts["iter_data"]

    return block_steps