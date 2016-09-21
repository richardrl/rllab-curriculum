# Tune for Montezuma's Revenge
# Try prioritized reset
# Use the Bellamre's ALE python interface, instead of OpenAI's
# This experiment does not use the resetter; it just tests the new environment interface

from __future__ import print_function
from __future__ import absolute_import

from sandbox.haoran.hashing.bonus_trpo.algos.bonus_trpo import BonusTRPO
from sandbox.haoran.hashing.bonus_trpo.bonus_evaluators.hashing_bonus_evaluator import HashingBonusEvaluator
from sandbox.haoran.tf.baselines.linear_feature_baseline import LinearFeatureBaseline
# from sandbox.haoran.tf.baselines.gaussian_mlp_baseline import GaussianMLPBaseline
from sandbox.haoran.tf.policies.categorical_mlp_policy import CategoricalMLPPolicy
# from sandbox.haoran.tf.policies.categorical_gru_policy import CategoricalGRUPolicy
from sandbox.haoran.tf.envs.base import TfEnv
from sandbox.haoran.tf.optimizers.conjugate_gradient_optimizer import ConjugateGradientOptimizer, FiniteDifferenceHvp
from rllab.misc.instrument import stub, run_experiment_lite
# from sandbox.haoran.hashing.bonus_trpo.envs.atari import AtariEnv
from sandbox.haoran.hashing.bonus_trpo.envs.atari_env import AtariEnv
from sandbox.haoran.hashing.bonus_trpo.resetter.atari_count_resetter import AtariCountResetter
from sandbox.haoran.myscripts.myutilities import get_time_stamp
from sandbox.haoran.ec2_info import instance_info, subnet_info
from rllab import config
import sys,os

stub(globals())
import tensorflow as tf

from rllab.misc.instrument import VariantGenerator, variant

"""
Fix to counting scheme. Fix config...
"""

exp_prefix = "bonus-trpo-atari/" + os.path.basename(__file__).split('.')[0] # exp_xxx
mode = "ec2"
ec2_instance = "c4.8xlarge"
subnet = "us-west-1c"

n_parallel = 4
snapshot_mode = "last"
plot = False
use_gpu = False # should change conv_type and ~/.theanorc
sync_s3_pkl = True
rom_folder = "sandbox/haoran/ale_python_interface/roms"


# params ---------------------------------------
batch_size = 50000
max_path_length = 4500
discount = 0.99
n_itr = 1000
record_internal_state = True

clip_reward = True
extra_dim_key = 1024
extra_bucket_sizes = [15485867, 15485917, 15485927, 15485933, 15485941, 15485959]

resetter_p = 1
resetter_exponent = 100 # only reset to new state


class VG(VariantGenerator):
    @variant
    def seed(self):
        return [111, 211, 311]

    @variant
    def bonus_coeff(self):
        return [0]

    @variant
    def dim_key(self):
        return [64]

    @variant
    def game(self):
        return ["frostbite"]

    @variant
    def bonus_form(self):
        return ["1/sqrt(n)"]

    @variant
    def death_ends_episode(self):
        return [False]

variants = VG().variants()


print("#Experiments: %d" % len(variants))
for v in variants:
    exp_name = "alex_{time}_{game}".format(
        time=get_time_stamp(),
        game=v["game"],
    )
    if ("ec2" in mode) and (len(exp_name) > 64):
        print("Should not use experiment name with length %d > 64.\nThe experiment name is %s.\n Exit now."%(len(exp_name),exp_name))
        sys.exit(1)

    # resetter = AtariCountResetter(
    #     p=resetter_p,
    #     exponent=resetter_exponent,
    # )
    resetter = None
    env = TfEnv(
        AtariEnv(
            rom_filename=os.path.join(rom_folder,v["game"]+".bin"),
            seed=v["seed"],
            obs_type="ram",
            record_image=False,
            record_ram=True,
            record_internal_state=True,
            resetter=resetter,
        )
    )
    policy = CategoricalMLPPolicy(env_spec=env.spec, hidden_sizes=(32, 32), name="policy")

    regressor_args = dict(
        hidden_sizes=(64,64),
        optimizer=None,
        use_trust_region=True,
        step_size=0.01,
        learn_std=False,
        init_std=1.0,
        normalize_inputs=True,
        normalize_outputs=True,
    )
    # baseline = GaussianMLPBaseline(env_spec=env.spec,regressor_args=regressor_args)
    baseline = LinearFeatureBaseline(env_spec=env.spec)
    bonus_evaluator = HashingBonusEvaluator(
        env_spec=env.spec,
        dim_key=v["dim_key"],
        bonus_form=v["bonus_form"],
        log_prefix="",
    )
    extra_bonus_evaluator = HashingBonusEvaluator(
        env_spec=env.spec,
        dim_key=extra_dim_key,
        bucket_sizes=extra_bucket_sizes,
        log_prefix="Extra",
    )
    algo = BonusTRPO(
        env=env,
        policy=policy,
        baseline=baseline,
        bonus_evaluator=bonus_evaluator,
        extra_bonus_evaluator=extra_bonus_evaluator,
        bonus_coeff=v["bonus_coeff"],
        batch_size=batch_size,
        max_path_length=max_path_length,
        discount=discount,
        n_itr=n_itr,
        clip_reward=clip_reward,
        plot=plot,
        optimizer=ConjugateGradientOptimizer(hvp_approach=FiniteDifferenceHvp(base_eps=1e-5))
    )

    # run --------------------------------------------------
    if "local_docker" in mode:
        actual_mode = "local_docker"
    elif "local" in mode:
        actual_mode = "local"
    elif "ec2" in mode:
        actual_mode = "ec2"
        # configure instance
        info = instance_info[ec2_instance]
        config.AWS_INSTANCE_TYPE = ec2_instance
        config.AWS_SPOT_PRICE = str(info["price"])
        n_parallel = int(info["vCPU"] /2)

        # choose subnet
        config.AWS_NETWORK_INTERFACES = [
            dict(
                SubnetId=subnet_info[subnet]["SubnetID"],
                Groups=subnet_info[subnet]["Groups"],
                DeviceIndex=0,
                AssociatePublicIpAddress=True,
            )
        ]
    else:
        raise NotImplementedError


    run_experiment_lite(
        algo.train(),
        exp_prefix=exp_prefix,
        exp_name=exp_name,
        seed=v["seed"],
        n_parallel=n_parallel,
        snapshot_mode=snapshot_mode,
        mode=actual_mode,
        variant=v,
        use_gpu=use_gpu,
        plot=plot,
        sync_s3_pkl=sync_s3_pkl,
    )

    if "test" in mode:
        sys.exit(0)

if ("local" not in mode) and ("test" not in mode):
    os.system("chmod 444 %s"%(__file__))
