"""
Symbolic States
"""
import pdb
import random
from collections import OrderedDict
import itertools
import os.path

import z3

import sage.all
from sage.all import cached_function

import vcommon as CM
import settings
from miscs import Miscs, Z3
from ds import Symbs, DSymbs, Inps, DTraces
from invs import Inv,  DInvs, Invs
import srcJava

dbg = pdb.set_trace
mlog = CM.getLogger(__name__, settings.logger_level)


class PC(object):
    def __init__(self, loc, depth, pcs, slocals, st, sd, use_reals):
        assert isinstance(loc, str) and loc, loc
        assert depth >= 0, depth
        assert isinstance(pcs, list) and \
            all(isinstance(pc, str) for pc in pcs), pcs
        assert isinstance(slocals, list) and \
            all(isinstance(slocal, str)
                for slocal in slocals) and slocals, slocals
        assert all(isinstance(s, str) and isinstance(t, str)
                   for s, t in st.iteritems()), st
        assert all(isinstance(s, str) and Miscs.is_expr(se)
                   for s, se in sd.iteritems()), sd
        assert isinstance(use_reals, bool), bool

        pcs_ = []
        pcsModIdxs = set()  # contains idxs of pc's with % (modulus ops)
        for i, p in enumerate(pcs):
            p, isReplaced = PC.replaceMod(p)
            if isReplaced:
                pcsModIdxs.add(i)
            sexpr = Miscs.msage_eval(p, sd)
            assert not isinstance(
                sexpr, bool), "pc '{}' evals to '{}'".format(p, sexpr)
            pcs_.append(sexpr)

        pcs = [Miscs.elim_denom(pc) for pc in pcs_]
        pcs = [pc for pc in pcs
               if not (pc.is_relational() and str(pc.lhs()) == str(pc.rhs()))]

        def thack0(s):
            # for Hola H32.Java program
            return s.replace("((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((j + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1) + 1)", "j + 100")

        slocals_ = []
        for p in slocals:
            try:
                sl = Miscs.msage_eval(p, sd)
            except MemoryError as mex:
                mlog.warn("{}: {}".format(mex, p))
                sl = Miscs.msage_eval(thack0(p), sd)

            slocals_.append(sl)
        slocals = slocals_
        slocals = [Miscs.elim_denom(p) for p in slocals]
        slocals = [p for p in slocals
                   if not (p.is_relational() and str(p.lhs()) == str(p.rhs()))]

        assert isinstance(loc, str) and loc, loc
        assert all(Miscs.is_rel(pc) for pc in pcs), pcs
        assert all(Miscs.is_rel(pc) for pc in slocals), slocals

        self.loc = loc
        self.depth = depth
        self.st = st
        self.pcs = pcs
        self.pcsModIdxs = pcsModIdxs
        self.slocals = slocals
        self.use_reals = use_reals

    def __str__(self):
        ss = ['loc: {}'.format(self.loc),
              'vs: {}'.format(', '.join('{} {}'.format(
                  self.st[v], v) for v in self.st)),
              'pcs: {}'.format(', '.join(map(str, self.pcs))),
              'slocals: {}'.format(', '.join(map(str, self.slocals)))]
        return '\n'.join(ss)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and hash(self) == hash(other)

    def __hash__(self):
        return hash(self.__str__())

    @property
    def pcs_z3(self):
        try:
            return self._pcs_z3
        except AttributeError:
            self._pcs_z3 = [Z3.toZ3(pc, self.use_reals,
                                    use_mod=i in self.pcsModIdxs)
                            for i, pc in enumerate(self.pcs)]
            return self._pcs_z3

    @property
    def slocals_z3(self):
        try:
            return self._slocals_z3
        except AttributeError:
            self._slocals_z3 = [Z3.toZ3(p, self.use_reals, use_mod=False)
                                for p in self.slocals]
            return self._slocals_z3

    @property
    def expr(self):
        constrs = self.pcs_z3 + self.slocals_z3
        return self.andConstrs(constrs)

    @property
    def exprPC(self):
        constrs = self.pcs_z3
        return self.andConstrs(constrs)

    @classmethod
    def andConstrs(cls, fs):
        assert all(z3.is_expr(f) for f in fs), fs

        f = z3.And(fs)
        f = z3.simplify(f)
        return f

    @classmethod
    def parsePC(cls, ss):
        assert isinstance(ss, list) and ss, ss

        curpart = []
        for s in ss:
            if 'loc: ' in s:
                loc = s.split()[1]  # e.g., vtrace30(I)V
                loc = loc.split('(')[0]  # vtrace30
                continue
            elif 'vars: ' in s:
                vs = s.split(':')[1].split(',')  # int x, int y
                vs = [tuple(tv.split()) for tv in vs if tv]
                pcs = curpart[1:]  # ignore pc constraint #
                curpart = []
                continue
            curpart.append(s)

        slocals = curpart[:]

        # some clean up
        def isTooLarge(p):
            if 'CON:' not in p:
                return False

            ps = p.split('=')
            assert len(ps) == 2
            v = sage.all.sage_eval(ps[1])
            if Miscs.isNum(v) and v >= settings.LARGE_N:
                mlog.warn("ignore {} (larger than {})".format(
                    p, settings.LARGE_N))
                return True
            else:
                return False

        slocals = [p for p in slocals if not isTooLarge(p)]
        slocals = [PC.replaceStr(p) for p in slocals if p]
        pcs = [PC.replaceStr(pc) for pc in pcs if pc]
        return loc, vs, pcs, slocals

    @classmethod
    def parse(cls, filename, delim="**********"):
        """
        Return a list of strings representing pc's
        """

        parts, curpart = [], []

        start = delim + " START"
        end = delim + " END"
        doAppend = False
        for l in CM.iread_strip(filename):
            if l.startswith(start):
                doAppend = True
                continue
            elif l.startswith(end):
                doAppend = False
                if curpart:
                    parts.append(curpart)
                    curpart = []
            else:
                if doAppend:
                    curpart.append(l)

        if not parts:
            mlog.error("Cannot obtain symstates from '{}'".format(filename))
            return None

        pcs = [cls.parsePC(pc) for pc in parts]
        return pcs

    @cached_function
    def replaceStr(s):
        s_ = (s.replace('&&', '').
              replace(' = ', '==').
              replace('CONST_', '').
              replace('REAL_', '').
              replace('%NonLinInteger%', '').
              replace('SYM:', '').
              replace('CON:', '').
              strip())
        return s_

    @cached_function
    def replaceMod(s):
        if "%" not in s:
            return s, False
        s_ = s.replace("%", "^")
        mlog.debug("Uninterpreted (temp hack): {} => {}".format(s, s_))
        return s_, True


class PCs(set):
    def __init__(self, loc, depth):
        assert isinstance(loc, str), loc
        assert depth >= 1, depth

        super(PCs, self).__init__(set())
        self.loc = loc
        self.depth = depth

    def add(self, pc):
        assert isinstance(pc, PC), pc
        super(PCs, self).add(pc)

    @property
    def expr(self):
        try:
            return self._expr
        except AttributeError:
            self._expr = z3.simplify(z3.Or([pc.expr for pc in self]))
            return self._expr

    @property
    def exprPC(self):
        try:
            return self._exprPC
        except AttributeError:
            self._exprPC = z3.simplify(z3.Or([pc.exprPC for pc in self]))
            return self._exprPC


class SymStates(object):
    def __init__(self, inp_decls, inv_decls):
        assert isinstance(inp_decls, Symbs), inp_decls  # I x, I y
        # {'vtrace1': (('q', 'I'), ('r', 'I'), ('x', 'I'), ('y', 'I'))}
        assert isinstance(inv_decls, DSymbs), inv_decls

        self.inp_decls = inp_decls
        self.inv_decls = inv_decls
        self.use_reals = inv_decls.use_reals
        self.inp_exprs = inp_decls.exprs(self.use_reals)

    def compute(self, filename, mainQName, clsName, jpfDir):

        def _f(d): return self.mk(
            d, filename, mainQName, clsName, jpfDir, len(self.inp_decls))

        mindepth = settings.JPF_MIN_DEPTH
        maxdepth = mindepth + settings.JPF_DEPTH_INCR
        tasks = [depth for depth in range(mindepth, maxdepth)]

        def f(tasks):
            rs = [(depth, _f(depth)) for depth in tasks]
            rs = [(depth, ss) for depth, ss in rs if ss]
            return rs
        wrs = Miscs.run_mp_simple("get symstates", tasks, f,
                                  doMP=settings.doMP)
        self.merge(wrs)

    @classmethod
    def mk(cls, depth, filename, mainQName, clsName, jpfDir, nInps):
        max_val = DTraces.inpMaxV
        ssfile = "{}.{}_{}_{}.straces".format(
            filename, mainQName, max_val, depth)

        mlog.debug("Obtain symbolic states (max val {}, tree depth {}){}"
                   .format(max_val, depth,
                           ' ({})'.format(ssfile) if os.path.isfile(ssfile)
                           else ''))

        if not os.path.isfile(ssfile):
            jpffile = srcJava.mkJPFRunFile(
                clsName, mainQName, jpfDir, nInps, max_val, depth)

            ssfile = os.path.join(
                jpfDir, "{}_{}_{}_{}.straces".format(
                    clsName, mainQName, max_val, depth))
            assert not os.path.isfile(ssfile), ssfile
            cmd = settings.JPF_RUN(jpffile=jpffile, tracefile=ssfile)
            mlog.debug(cmd)
            CM.vcmd(cmd)

        pcs = PC.parse(ssfile)
        return pcs

    def merge(self, depthss):
        """
        Merge PC's info into symbolic states sd[loc][depth]
        """
        assert isinstance(depthss, list) and depthss, depthss
        assert all(depth >= 1 and isinstance(ss, list)
                   for depth, ss in depthss), depthss

        symstates = {}
        ssd = {}  # symb:string -> symbols:sage_expr
        for depth, ss in depthss:
            for (loc, vs, pcs, slocals) in ss:
                sst = OrderedDict((s, t)
                                  for t, s in vs)  # symb:str -> types:str
                for _, s in vs:
                    if s not in ssd:
                        ssd[s] = sage.all.var(s)
                pc = PC(loc, depth, pcs, slocals, sst, ssd, self.use_reals)

                symstates.setdefault(loc, {})
                symstates[loc].setdefault(depth, PCs(loc, depth)).add(pc)

        # only store incremental states at each depth
        for loc in symstates:
            depths = sorted(symstates[loc])
            assert len(depths) >= 2, depths
            for i in range(len(depths)):
                if i == 0:
                    pass
                iss = symstates[loc][depths[i]]
                for j in range(i):
                    jss = symstates[loc][depths[j]]
                    assert jss.issubset(iss)
                    assert len(jss) <= len(iss), (len(jss), len(iss))

                # only keep diffs
                for j in range(i):
                    jss = symstates[loc][depths[j]]
                    for s in jss:
                        assert s in iss, s
                        iss.remove(s)

        # clean up
        empties = [(loc, depth) for loc in symstates
                   for depth in symstates[loc] if not symstates[loc][depth]]
        for loc, depth in empties:
            mlog.warn(
                "{}: depth {}: no symbolic states found".format(loc, depth))
            symstates[loc].pop(depth)

        empties = [loc for loc in symstates if not symstates[loc]]
        for loc in empties:
            mlog.warn("{}: no symbolic states found".format(loc))
            symstates.pop(loc)

        if all(not symstates[loc] for loc in symstates):
            mlog.error("No symbolic states found for any locs. Exit !!")
            exit(1)

        # output info
        mlog.debug('\n'.join("{}: depth {}: {} symstates\n{}".format(
            loc, depth, len(symstates[loc][depth]),
            '\n'.join("{}. {}".format(i, ss)
                      for i, ss in enumerate(symstates[loc][depth])))
            for loc in symstates for depth in symstates[loc]))

        self.ss = symstates

    def get_inps(self, dinvs, inps, path_idx=None):
        """call verifier on each inv"""

        def check(loc, inv):
            return self.mcheck_d(
                loc, path_idx, inv.expr(self.use_reals), inps, ncexs=1)

        tasks = [(loc, inv) for loc in dinvs for inv in dinvs[loc]
                 if inv.stat is None]
        refsD = {(loc, str(inv)): inv for loc, inv in tasks}

        def f(tasks):
            return [(loc, str(inv), check(loc, inv)) for loc, inv in tasks]
        wrs = Miscs.run_mp_simple("prove", tasks, f, doMP=settings.doMP)

        mCexs, mdinvs = [], DInvs()
        for loc, str_inv, (cexs, isSucc) in wrs:
            inv = refsD[(loc, str_inv)]

            if cexs:
                stat = Inv.DISPROVED
                mCexs.append({loc: {str(inv): cexs}})
            else:
                stat = Inv.PROVED if isSucc else Inv.UNKNOWN
            inv.stat = stat
            mdinvs.setdefault(loc, Invs()).add(inv)

        return merge(mCexs), mdinvs

    def check(self, dinvs, inps, path_idx=None):
        """
        Check invs.
        Also update inps
        """
        assert isinstance(dinvs, DInvs), dinvs
        assert not inps or (isinstance(inps, Inps) and inps), inps

        mlog.debug("checking {} invs:\n{}".format(dinvs.siz, dinvs))
        return self.get_inps(dinvs, inps, path_idx)

    def mkInpsConstr(self, inps):
        cstrs = []
        if isinstance(inps, Inps) and inps:
            inpCstrs = [inp.mkExpr(self.inp_exprs) for inp in inps]
            inpCstrs = [z3.Not(expr) for expr in inpCstrs if expr is not None]
            cstrs.extend(inpCstrs)

        if not cstrs:
            return None
        elif len(cstrs) == 1:
            return cstrs[0]
        else:
            return z3.And(cstrs)

    def mcheck(self, symstatesExpr, inv, inps, ncexs=1):
        """
        check if pathcond => inv
        if not, return cex

        return inps, cexs, isSucc (if the solver does not timeout)
        """
        assert z3.is_expr(symstatesExpr), symstatesExpr
        assert inv is None or z3.is_expr(inv), inv
        assert inps is None or isinstance(inps, Inps), inps
        assert ncexs >= 0, ncexs

        f = symstatesExpr
        iconstr = self.mkInpsConstr(inps)
        if iconstr is not None:
            f = z3.simplify(z3.And(iconstr, f))
        if inv is not None:
            f = z3.Not(z3.Implies(f, inv))

        models, stat = Z3.get_models(f, ncexs)
        cexs, isSucc = Z3.extract(models)
        return cexs, isSucc, stat

    def mcheck_d(self, loc, path_idx, inv, inps, ncexs=1):
        assert isinstance(loc, str), loc
        assert path_idx is None or path_idx >= 0
        assert inv is None or z3.is_expr(inv), inv
        assert inps is None or isinstance(inps, Inps), inps
        assert ncexs >= 1, ncexs

        if inv == z3.BoolVal(False):
            inv = None

        def f(depth):
            ss = self.ss[loc][depth]
            if inv == z3.BoolVal(False):
                ss = ss[path_idx].exprPC if path_idx else ss.exprPC
            else:
                ss = ss[path_idx].expr if path_idx else ss.expr
            return self.mcheck(ss, inv, inps, ncexs)

        depths = sorted(self.ss[loc].keys())
        depth_idx = 0

        cexs, isSucc, stat = f(depths[depth_idx])
        while(stat != z3.sat and depth_idx < len(depths) - 1):
            depth_idx = depth_idx + 1
            cexs_, isSucc_, stat_ = f(depths[depth_idx])
            if stat_ != stat:
                mlog.debug("depth diff {}: {} @ depth {} vs {} @ depth {}"
                           .format(inv, stat_, depths[depth_idx - 1],
                                   stat, depths[depth_idx]))
            cexs, isSucc, stat = cexs_, isSucc_, stat_

        return cexs, isSucc

    def extractCexs(self, models):
        assert all(isinstance(m, z3.ModelRef)
                   for m in models) and models, models

        def f(model):
            cex = {str(s): sage.all.sage_eval(str(model[s])) for s in model}
            return cex

        cexs = [f(model) for model in models]
        return cexs

    # def gen_rand_inps(self, prog):
    #     def _f(irs): return tuple(random.randrange(ir[0], ir[1]) for ir in irs)

    #     try:
    #         valid_ranges = self._valid_ranges
    #         valid_inps = set()
    #     except AttributeError:  # compute rranges
    #         tiny = 0.05
    #         small = 0.10
    #         large = 1 - small
    #         maxV = DTraces.inpMaxV
    #         minV = -1 * maxV
    #         rinps = [(0, int(maxV * small)), (0, int(maxV * tiny)),
    #                  (int(maxV * large), maxV),
    #                  (int(minV * small), 0), (int(minV * tiny), 0),
    #                  (minV, int(minV * large))]

    #         # [((0, 30), (0, 30)), ((0, 30), (270, 300)), ...]
    #         rinps = list(itertools.product(
    #             *itertools.repeat(rinps, len(self.inp_exprs))))
    #         valid_ranges, valid_inps = set(), set()
    #         for rinp in rinps:
    #             inp = _f(rinp)
    #             myinps = Inps()
    #             myinps.myupdate(set([inp]), self.inp_decls.names)
    #             tcs = prog.get_traces(myinps)
    #             if tcs:
    #                 valid_ranges.add(rinp)
    #                 valid_inps.add(inp)
    #             else:
    #                 mlog.debug("inp range {} invalid".format(inp))

    #         self._valid_ranges = valid_ranges

    #     # gen inps
    #     if not valid_inps:
    #         valid_inps = set(_f(vr) for vr in valid_ranges)
    #     return valid_inps


def merge(ds):
    newD = {}
    for d in ds:
        for loc in d:
            assert d[loc]
            newD.setdefault(loc, {})
            for inv in d[loc]:
                assert d[loc][inv]
                newD[loc].setdefault(inv, [])
                for e in d[loc][inv]:
                    newD[loc][inv].append(e)
    return newD
