import sys
import os.path
import datetime
import time
import helpers.vcommon


def run(inp, seed, maxdeg, do_rmtmp):

    import alg
    if inp.endswith(".java") or inp.endswith(".class"):
        dig = alg.DigSymStates(inp)
    else:
        dig = alg.DigTraces(inp)

    invs, traces, tmpdir = dig.start(seed, maxdeg)

    if do_rmtmp:
        import shutil
        print("clean up: rm -rf {}".format(tmpdir))
        shutil.rmtree(tmpdir)
    else:
        print("tmpdir: {}".format(tmpdir))


if __name__ == "__main__":
    import argparse
    aparser = argparse.ArgumentParser("DIG")
    ag = aparser.add_argument

    ag("inp", help="inp")

    # 0 Error #1 Warn #2 Info #3 Debug #4 Detail
    ag("--log_level", "-log_level",
       type=int,
       choices=range(5),
       default=2,
       help="set logger info")

    ag("--seed", "-seed",
       type=float,
       help="use this seed")

    ag("--maxdeg", "-maxdeg",
       type=int,
       default=None,
       help="find nonlinear invs up to degree")

    ag("--maxterm", "-maxterm",
       type=int,
       default=None,
       help="autodegree")

    ag("--inpMaxV", "-inpMaxV",
       type=int,
       help="max inp value")

    ag("--jpfmindepth", "-jpfmindepth",
       type=int,
       help="JPF depthlimit")

    ag("--octmaxv", "-octmaxv",
       type=int,
       help="max val for oct ieqs")

    ag("--eqtrate", "-eqtrate",
       type=float,
       help="Equation rate multiplier")

    ag("--noeqts", "-noeqts",
       action="store_true")

    ag("--noieqs", "-noieqs",
       action="store_true")

    ag("--nominmaxplus", "-nominmaxplus",
       action="store_true")

    ag("--nopreposts", "-nopreposts",
       action="store_true")

    ag("--nomp", "-nomp",
       action="store_true",
       help="don't use multiprocessing")

    ag("--normtmp", "-normtmp",
       action="store_true")

    args = aparser.parse_args()

    import settings
    settings.DO_MP = not args.nomp
    settings.DO_EQTS = not args.noeqts
    settings.DO_IEQS = not args.noieqs
    settings.DO_MINMAXPLUS = not args.nominmaxplus
    settings.DO_PREPOSTS = not args.nopreposts

    if 0 <= args.log_level <= 4 and args.log_level != settings.logger_level:
        settings.logger_level = args.log_level
    settings.logger_level = helpers.vcommon.getLogLevel(settings.logger_level)

    mlog = helpers.vcommon.getLogger(__name__, settings.logger_level)

    if args.inpMaxV >= 1 and args.inpMaxV != settings.INP_MAX_V:
        settings.INP_MAX_V = args.inpMaxV

    if args.eqtrate >= 1 and args.eqtrate != settings.EQT_RATE:
        settings.EQT_RATE = args.eqtrate

    if args.jpfmindepth >= 1 and args.jpfmindepth != settings.JPF_MIN_DEPTH:
        settings.JPF_MIN_DEPTH = args.jpfmindepth

    if args.octmaxv >= 1 and args.octmaxv != settings.OCT_MAX_V:
        settings.OCT_MAX_V = args.octmaxv

    if args.maxterm >= 1 and args.maxterm != settings.MAX_TERM:
        settings.MAX_TERM = args.maxterm

    mlog.info("{}: {}".format(datetime.datetime.now(), ' '.join(sys.argv)))

    if __debug__:
        mlog.warn("DEBUG MODE ON. Can be slow !")

    inp = os.path.realpath(os.path.expanduser(args.inp))
    seed = round(time.time(), 2) if args.seed is None else float(args.seed)

    run(inp, seed, maxdeg=args.maxdeg, do_rmtmp=not args.normtmp)
