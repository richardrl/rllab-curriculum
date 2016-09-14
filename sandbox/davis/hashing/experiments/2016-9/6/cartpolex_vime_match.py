from __future__ import print_function
from __future__ import absolute_import

info = """Reconciling CartpoleSwingupEnvX experiments with VIME results."""

from rllab.misc.instrument import stub, run_experiment_lite
from rllab.baselines.gaussian_mlp_baseline import GaussianMLPBaseline
from rllab.envs.normalized_env import normalize
from sandbox.rocky.hashing.algos.bonus_trpo import BonusTRPO
from sandbox.rocky.hashing.bonus_evaluators.hashing_bonus_evaluator import HashingBonusEvaluator
from sandbox.rein.envs.mountain_car_env_x import MountainCarEnvX
from sandbox.rein.envs.cartpole_swingup_env_x import CartpoleSwingupEnvX
from sandbox.rein.envs.double_pendulum_env_x import DoublePendulumEnvX
from sandbox.rein.envs.half_cheetah_env_x import HalfCheetahEnvX
from sandbox.rein.envs.swimmer_env_x import SwimmerEnvX
from sandbox.rein.envs.walker2d_env_x import Walker2DEnvX
from rllab.envs.mujoco.gather.swimmer_gather_env import SwimmerGatherEnv
from sandbox.rocky.tf.policies.gaussian_mlp_policy import GaussianMLPPolicy
from sandbox.rocky.tf.envs.base import TfEnv

import sys
import argparse

stub(globals())

from rllab.misc.instrument import VariantGenerator
from rllab.envs.mujoco.gather.swimmer_gather_env import SwimmerGatherEnv as SGE

# horizon 500
# batch size 5000
# swimmergather batch size 50000
# discretize state
# lower dimension
# robustness to noise (in simpler tasks)?
# count state-action pairs?
# log state count

# baselines for comparison:
#   prediction error
#   just add constant value (encourage to be alive)

N_ITR = 1000
N_ITR_DEBUG = 5

envs = [CartpoleSwingupEnvX()]


def experiment_variant_generator():
    vg = VariantGenerator()
    vg.add("env", map(TfEnv, envs), hide=True)
    vg.add("batch_size", [1000, 5000], hide=True)
    vg.add("step_size", [0.01], hide=True)
    vg.add("max_path_length", [500], hide=True)
    vg.add("discount", [0.995], hide=True)
    vg.add("seed", range(10), hide=True)
    vg.add("bonus_coeff", [0, 0.001, 0.01, 0.1])
    vg.add("bonus_evaluator",
           lambda env: [HashingBonusEvaluator(env.spec)],
           hide=True)
    vg.add("baseline",
           lambda env: [GaussianMLPBaseline(env.spec, regressor_args=dict(hidden_sizes=(32,),
                                                                          batchsize=1000000))],
           hide=True)
    return vg


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--local",
                        help="run experiment locally",
                        action="store_true")
    parser.add_argument("-v", "--visualize",
                        help="visualize simulations during experiment",
                        action="store_true")
    parser.add_argument("-d", "--debug",
                        help="run in debug mode (only one configuration; don't terminate machines)",
                        action="store_true")
    parser.add_argument("-i", "--info",
                        help="display experiment info (without running experiment)",
                        action="store_true")
    parser.add_argument("-n", "--n-itr", type=int,
                        help="number of iterations (overrides default; mainly for debugging)")
    args = parser.parse_args()
    if args.info:
        print(info.replace('\n', ' '))
        sys.exit(0)
    return args

if __name__ == '__main__':
    args = parse_args()
    exp_prefix = __file__.split('/')[-1][:-3].replace('_', '-')
    if args.debug:
        exp_prefix += '-DEBUG'
    N_ITR = args.n_itr if args.n_itr is not None else N_ITR_DEBUG if args.debug else N_ITR
    vg = experiment_variant_generator()
    variants = vg.variants()
    print("Running experiment {}.".format(exp_prefix))
    print("Number of experiments to run: {}.".format(len(variants) if not args.debug else 1))
    for variant in variants:
        exp_name = vg.to_name_suffix(variant)
        if exp_name == '':
            exp_name = None

        policy = GaussianMLPPolicy(
            name="policy",
            env_spec=variant["env"].spec,
            hidden_sizes=(32,),
        )

        algo = BonusTRPO(
            bonus_evaluator=variant["bonus_evaluator"],
            bonus_coeff=variant["bonus_coeff"],
            env=variant["env"],
            policy=policy,
            baseline=variant["baseline"],
            batch_size=variant["batch_size"],
            whole_paths=True,
            max_path_length=variant["max_path_length"],
            n_itr=N_ITR,
            discount=variant["discount"],
            step_size=variant["step_size"],
            optimizer_args=dict(
                # num_slices=1,
                subsample_factor=0.1),
            plot=args.visualize and args.local,
        )

        run_experiment_lite(
            algo.train(),
            n_parallel=1,
            snapshot_mode="last",
            seed=variant["seed"],
            plot=args.visualize and args.local,
            mode="local" if args.local else "ec2",
            exp_prefix=exp_prefix,
            terminate_machine=not args.debug
        )

        if args.debug:
            break  # Only run first experiment variant in debug mode
