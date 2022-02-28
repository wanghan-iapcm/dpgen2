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

import os
from typing import Set, List
from pathlib import Path


class ConcurrentLearningBlock(Steps):
    def __init__(
            self,
            name : str,
            prep_run_dp_train_op : OP,
            prep_run_lmp_op : OP,
            select_confs_op : OP,
            prep_run_fp_op : OP,
            collect_data_op : OP,
            select_confs_image : str = "dflow:v1.0",
            collect_data_image : str = "dflow:v1.0",
            upload_python_package : str = None,
    ):
        self._input_parameters={
            "block_id" : InputParameter(),
            "type_map" : InputParameter(),
            "numb_models": InputParameter(type=int),
            "template_script" : InputParameter(),
            "train_config" : InputParameter(),
            "lmp_config" : InputParameter(),
            "conf_selector" : InputParameter(),
            "fp_inputs" : InputParameter(),
            "fp_config" : InputParameter(),
        }
        self._input_artifacts={
            "lmp_task_grp" : InputArtifact(),
            "init_models" : InputArtifact(),
            "init_data" : InputArtifact(),
            "iter_data" : InputArtifact(),
        }
        self._output_parameters={
            "exploration_report": OutputParameter(),
        }
        self._output_artifacts={
            "models": OutputArtifact(),
            "iter_data" : OutputArtifact(),
            "trajs" : OutputArtifact(),
        }
        
        super().__init__(
            name = name,
            inputs = Inputs(
                parameters=self._input_parameters,
                artifacts=self._input_artifacts,
            ),
            outputs=Outputs(
                parameters=self._output_parameters,
                artifacts=self._output_artifacts,
            ),
        )

        self._my_keys = ['select-confs', 'collect-data']
        self._keys = \
            prep_run_dp_train_op.keys + \
            prep_run_lmp_op.keys + \
            self._my_keys[:1] + \
            prep_run_fp_op.keys + \
            self._my_keys[1:2]
        self.step_keys = {}
        for ii in self._my_keys:
            self.step_keys[ii] = '--'.join(
                ["%s"%self.inputs.parameters["block_id"], ii]
            )

        self = _block_cl(
            self,
            self.step_keys,
            name,
            prep_run_dp_train_op,
            prep_run_lmp_op,
            select_confs_op,
            prep_run_fp_op,
            collect_data_op,
            select_confs_image = select_confs_image,
            collect_data_image = collect_data_image,
            upload_python_package = upload_python_package,
        )

    @property
    def input_parameters(self):
        return self._input_parameters

    @property
    def input_artifacts(self):
        return self._input_artifacts

    @property
    def output_parameters(self):
        return self._output_parameters

    @property
    def output_artifacts(self):
        return self._output_artifacts

    @property
    def keys(self):
        return self._keys


def _block_cl(
        block_steps : Steps,
        step_keys : List[str],
        name : str,
        prep_run_dp_train_op : OP,
        prep_run_lmp_op : OP,
        select_confs_op : OP,
        prep_run_fp_op : OP,
        collect_data_op : OP,
        select_confs_image : str = "dflow:v1.0",
        collect_data_image : str = "dflow:v1.0",
        upload_python_package : str = None,
):

    prep_run_dp_train = Step(
        name + '-prep-run-dp-train',
        template = prep_run_dp_train_op,
        parameters={
            "block_id" : block_steps.inputs.parameters['block_id'],
            "train_config" : block_steps.inputs.parameters['train_config'],
            "numb_models": block_steps.inputs.parameters['numb_models'],
            "template_script": block_steps.inputs.parameters['template_script'],
        },
        artifacts={
            "init_models" : block_steps.inputs.artifacts['init_models'],
            "init_data" : block_steps.inputs.artifacts['init_data'],
            "iter_data" : block_steps.inputs.artifacts['iter_data'],
        },
        key = '--'.join(["%s"%block_steps.inputs.parameters["block_id"], "prep-run-train"]),
    )
    block_steps.add(prep_run_dp_train)
        
    prep_run_lmp = Step(
        name = name + '-prep-run-lmp',
        template = prep_run_lmp_op,
        parameters={
            "block_id" : block_steps.inputs.parameters['block_id'],
            "lmp_config": block_steps.inputs.parameters['lmp_config'],
        },
        artifacts={
            "lmp_task_grp": block_steps.inputs.artifacts['lmp_task_grp'],
            "models" : prep_run_dp_train.outputs.artifacts['models'],
        },
        key = '--'.join(["%s"%block_steps.inputs.parameters["block_id"], "prep-run-lmp"]),
    )
    block_steps.add(prep_run_lmp)
        
    select_confs = Step(
        name = name + '-select-confs',
        template=PythonOPTemplate(
            select_confs_op,
            image=select_confs_image,
            output_artifact_archive={
                "confs": None
            },
            python_packages = upload_python_package,
        ),
        parameters={
            "conf_selector": block_steps.inputs.parameters['conf_selector'],
            "type_map": block_steps.inputs.parameters['type_map'],
            "traj_fmt": 'lammps/dump',
        },
        artifacts={
            "trajs" : prep_run_lmp.outputs.artifacts['trajs'],
            "model_devis" : prep_run_lmp.outputs.artifacts['model_devis'],
        },
        key = step_keys['select-confs'],
    )
    block_steps.add(select_confs)
        
    prep_run_fp = Step(
        name = name + '-prep-run-fp',
        template = prep_run_fp_op,
        parameters={
            "block_id" : block_steps.inputs.parameters['block_id'],
            "inputs": block_steps.inputs.parameters['fp_inputs'],            
            "fp_config": block_steps.inputs.parameters['fp_config'],            
        },
        artifacts={
            "confs" : select_confs.outputs.artifacts['confs'],
        },
        key = '--'.join(["%s"%block_steps.inputs.parameters["block_id"], "prep-run-fp"]),
    )
    block_steps.add(prep_run_fp)

    collect_data = Step(
        name = name + '-collect-data',
        template=PythonOPTemplate(
            collect_data_op,
            image=collect_data_image,
            output_artifact_archive={
                "iter_data": None
            },
            python_packages = upload_python_package,
        ),
        parameters={
            "name": block_steps.inputs.parameters["block_id"],
        },
        artifacts={
            "iter_data" : block_steps.inputs.artifacts['iter_data'],
            "labeled_data" : prep_run_fp.outputs.artifacts['labeled_data'],
        },
        key = step_keys['collect-data'],
    )
    block_steps.add(collect_data)

    block_steps.outputs.parameters["exploration_report"].value_from_parameter = \
        select_confs.outputs.parameters["report"]
    block_steps.outputs.artifacts["models"]._from = \
        prep_run_dp_train.outputs.artifacts["models"]
    block_steps.outputs.artifacts["iter_data"]._from = \
        collect_data.outputs.artifacts["iter_data"]
    block_steps.outputs.artifacts["trajs"]._from = \
        prep_run_lmp.outputs.artifacts["trajs"]

    return block_steps
