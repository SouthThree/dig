from abc import ABCMeta
import os.path
from time import time
import sage.all
import vcommon as CM
from miscs import Miscs, Z3
import srcJava
from ds import Inps, Traces, DTraces, Inv, Invs, DInvs, Prog
from symstates import SymStates
from cegir import Cegir
from cegirEqts import CegirEqts
from cegirIeqs import CegirIeqs

import settings
mlog = CM.getLogger(__name__, settings.logger_level)


class Dig(object):
    __metaclass__ = ABCMeta

    def __init__(self, filename):
        assert os.path.isfile(filename), filename
        mlog.info("analyze '{}'".format(filename))

        import tempfile
        self.tmpdir = tempfile.mkdtemp(dir=settings.tmpdir, prefix="Dig_")
        self.filename = filename

    def start(self, seed, maxdeg, doEqts, doIeqs):
        assert maxdeg is None or maxdeg >= 1, maxdeg
        assert isinstance(doEqts, bool), doEqts
        assert isinstance(doIeqs, bool), doIeqs

        import random
        random.seed(seed)
        sage.all.set_random_seed(seed)
        mlog.debug("set seed to: {} (test {})".format(
            seed, sage.all.randint(0, 100)))

        # determine degree
        maxvars = max(self.invDecls.itervalues(), key=lambda d: len(d))
        deg = Miscs.getAutoDeg(maxdeg, len(maxvars))
        return deg

    def uniqify(self, dinvs):
        assert isinstance(dinvs, DInvs) and dinvs, dinvs

        mlog.info("uniqify {} invs".format(dinvs.siz))
        st = time()
        mlog.debug("{}".format(dinvs.__str__(printStat=True)))
        oldSiz = dinvs.siz

        # save stats info
        statsd = {
            loc: {inv.inv: inv.stat for inv in dinvs[loc]} for loc in dinvs}

        def wprocess(tasks, Q):
            rs = [(loc, Z3.reduceSMT(invs, self.symstates.useReals))
                  for loc, invs in tasks]
            if Q is None:
                return rs
            else:
                Q.put(rs)

        tasks = [(loc, [inv.inv for inv in dinvs[loc]]) for loc in dinvs]
        wrs = Miscs.runMP("uniqify", tasks, wprocess, chunksiz=1,
                          doMP=settings.doMP and len(tasks) >= 2)

        dinvs = DInvs((
            loc, Invs(Inv(inv, stat=statsd[loc][inv]) for inv in invs)
        ) for loc, invs in wrs if invs)

        mlog.debug("uniqify: remove {} redundant invs ({}s)"
                   .format(oldSiz - dinvs.siz, time() - st))
        return dinvs

    def postprocess(self, dinvs, traces, inps, st):
        assert isinstance(dinvs, DInvs), dinvs
        assert isinstance(traces, DTraces), traces
        assert isinstance(inps, Inps), inps
        assert st >= 0.0, st

        mlog.info("test {} invs on {} traces".format(dinvs.siz, traces.siz))
        dinvs = dinvs.testTraces(traces)
        dinvs = self.uniqify(dinvs)

        # print results
        result_str = ("*** '{}', {} locs, invs {} ({} eqts), inps {} "
                      "time {:02f} s, rand {}:\n{}")
        print(result_str.format(self.filename, len(dinvs),
                                dinvs.siz, dinvs.nEqs, len(inps),
                                time() - st, sage.all.randint(0, 100),
                                dinvs.__str__(printStat=True)))


class DigCegir(Dig):
    def __init__(self, filename):
        super(DigCegir, self).__init__(filename)

        # call ASM to obtain
        (inpDecls, invDecls, clsName, mainQName, jpfDir, jpfFile,
         traceDir, traceFile) = srcJava.parse(filename, self.tmpdir)

        self.inpDecls = inpDecls
        self.invDecls = invDecls
        self.useRandInit = True

        exeCmd = "java -ea -cp {} {}".format(traceDir, clsName)
        self.prog = Prog(exeCmd, traceDir, invDecls)

        self.symstates = SymStates(inpDecls, invDecls)
        self.symstates.compute(self.filename, mainQName, clsName, jpfDir)
        invalidLocs = [loc for loc in invDecls if loc not in self.symstates.ss]
        for loc in invalidLocs:
            self.invDecls.pop(loc)

    def strOfLocs(self, locs):
        return '; '.join("{} ({})".format(l, self.invDecls[l]) for l in locs)

    def start(self, seed, maxdeg, doEqts, doIeqs):
        deg = super(DigCegir, self).start(seed, maxdeg, doEqts, doIeqs)
        st = time()
        solver = Cegir(self.symstates, self.prog)
        mlog.debug("check reachability")
        dinvs, traces, inps = solver.checkReach()
        if not traces:
            return dinvs, traces, self.tmpdir

        def _gen(typ):

            st_gen = time()
            cls = CegirEqts if typ == 'eqts' else CegirIeqs
            mlog.info("gen {} at {} locs".format(typ, len(traces)))
            mlog.debug(self.strOfLocs(traces.keys()))
            solver = cls(self.symstates, self.prog)

            solver.useRandInit = self.useRandInit
            invs = solver.gen(deg, traces, inps)

            if not invs:
                mlog.warn("found no {}".format(typ))
                return

            mlog.info("infer {} {} in {}s"
                      .format(invs.siz, typ, time() - st_gen))
            if invs:
                dinvs.merge(invs)
                mlog.debug("{}".format(dinvs.__str__(printStat=True)))

        if doEqts:
            _gen('eqts')
        if doIeqs:
            _gen('ieqs')

        self.postprocess(dinvs, traces, inps, st)
        return dinvs, traces, self.tmpdir


class DigTraces(Dig):
    def __init__(self, filename):
        super(DigTraces, self).__init__(filename)
        from srcTcs import Src
        self.src = Src(filename)
        self.invDecls = self.src.getInvDecls()

    def start(self, seed, maxdeg, doEqts, doIeqs):

        deg = super(DigTraces, self).start(
            seed, maxdeg, doEqts, doIeqs)

        st = time()
        loc = self.invDecls.keys()[0]
        dinvs = DInvs()
        dinvs[loc] = Invs()

        vs = tuple(self.invDecls[loc].keys())
        assert vs, vs

        from ds import _Trace
        traces = [l.split()
                  for loc_, l in self.src.contentsd.iteritems()
                  if str(loc_) != loc]
        traces = [[t[i] for i in range(len(vs))] for t in traces]
        traces = [_Trace.parse(vs, t) for t in traces]
        traces = Traces(set(traces))

        eqtrate = settings.eqtrate
        terms, template, uks, nEqtsNeeded = Miscs.initTerms(
            vs, deg, eqtrate)

        exprs = list(traces.instantiate(template, nEqtsNeeded))
        eqts = Miscs.solveEqts(exprs, uks, template)
        for inv in eqts:
            dinvs[loc].add(Inv(inv))

        dtraces = DTraces()
        dtraces[loc] = traces
        inps = Inps()
        self.postprocess(dinvs, dtraces, inps, st)

        return dinvs, None, self.tmpdir