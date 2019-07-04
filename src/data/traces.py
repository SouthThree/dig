import pdb
from collections import namedtuple
import z3
import sage.all

import helpers.vcommon as CM
from helpers.miscs import Miscs
import settings

import data.miscs

DBG = pdb.set_trace
mlog = CM.getLogger(__name__, settings.logger_level)


class SymbsVals(namedtuple('SymbsVals', ('ss', 'vs'))):
    """"
    ((x, y), (3, 4))
    """

    def __str__(self):
        return ','.join('{}={}'.format(s, v) for s, v in zip(self.ss, self.vs))


class SymbsValsSet(set):
    def __init__(self, myset=set()):
        assert all(isinstance(t, SymbsVals) for t in myset), myset
        super(SymbsValsSet, self).__init__(myset)

    def __contains__(self, t):
        assert isinstance(t, SymbsVals), t
        return super(SymbsValsSet, self).__contains__(t)

    def add(self, t):
        assert isinstance(t, SymbsVals), t
        return super(SymbsValsSet, self).add(t)


class Trace(SymbsVals):
    maxVal = 100000000

    @property
    def mydict(self):
        # use for expression substitution
        try:
            return self._mydict
        except AttributeError:
            self._mydict = {sage.all.var(s): v for s, v
                            in zip(self.ss, self.vs) if "!" not in s}

            return self._mydict

    @property
    def mydict_str(self):
        # use for maxplus eval
        try:
            return self._mydict_str
        except AttributeError:
            self._mydict_str = {s: v for s, v in zip(self.ss, self.vs)
                                if "!" not in s}
            return self._mydict_str

    @classmethod
    def parse(cls, ss, vs):
        assert isinstance(ss, (tuple, list)), ss
        assert isinstance(vs, (tuple, list)), vs

        vs = tuple(Miscs.ratOfStr(t) for t in vs)
        return Trace(ss, vs)

    @classmethod
    def fromDict(cls, d):
        # {'y': 1, 'x': 2, 'r': 2, 'b': 2}
        ss = tuple(sorted(d))
        vs = tuple(d[s] for s in ss)
        return cls(ss, vs)

    def myeval(self, expr):
        assert Miscs.is_expr(expr), expr
        rs = expr.subs(self.mydict)
        return rs

    def mkExpr(self, ss):
        # create z3 expression

        assert len(ss) == len(self.vs), (ss, self.vs)
        try:
            exprs = [s == v for s, v in zip(ss, self.vs)]
        except Exception:
            myvals = map(int, self.vs)
            exprs = [s == v for s, v in zip(ss, myvals)]
        return z3.And(exprs)


class Traces(SymbsValsSet):

    def __str__(self, printDetails=False):
        if printDetails:
            return ", ".join(map(str, sorted(self)))
        else:
            return str(len(self))

    def myeval(self, expr):
        assert Miscs.is_expr(expr), expr
        return [trace.myeval(expr) for trace in self]

    @classmethod
    def extract(cls, cexs, useOne=True):
        """
        cexs is a dict{inv: [dict]}
        for each disproved inv, use just 1 cex
        """

        if useOne:
            cexs = [cexs[inv][0] for inv in cexs]
        else:
            cexs = [cex for inv in cexs for cex in cexs[inv]]

        cexs = [Trace.fromDict(cex) for cex in cexs]
        cexs = Traces(cexs)
        return cexs

    @property
    def mydicts(self):
        return (trace.mydict for trace in self)

    def instantiate(self, term, nTraces):
        assert Miscs.is_expr(term), term
        assert nTraces is None or nTraces >= 1, nTraces

        if nTraces is None:
            for t in self.mydicts:
                exprs = set(term.subs(t) for t in self.mydicts)
        else:
            nTracesExtra = nTraces * settings.TRACE_MULTIPLIER
            exprs = set()
            for t in self.mydicts:
                expr = term.subs(t)
                if expr not in exprs:
                    exprs.add(expr)
                    if len(exprs) >= nTracesExtra:
                        break

            # instead of doing this, can find out the # 0's in traces
            # the more 0's , the better
            exprs = sorted(exprs, key=lambda expr: len(Miscs.getVars(expr)))
            exprs = set(exprs[:nTraces])
        return exprs

    def get_satisfying_traces(self, inv):
        return Traces([t for t in self if inv.test_single_trace(t)])

    def padZeros(self, ss):
        newTraces = Traces()
        for t in self:
            tss = set(t.ss)
            if len(tss) < len(ss):
                ss_ = ss - tss
                newss = t.ss + tuple(ss_)
                newvs = t.vs + (0,) * len(ss_)
                t = Trace(newss, newvs)
            newTraces.add(t)

        return newTraces


class DTraces(dict):
    """
    {loc: Traces}
    """

    @property
    def siz(self): return sum(map(len, self.itervalues()))

    def __str__(self, printDetails=False):
        return "\n".join("{}: {}".format(loc, traces.__str__(printDetails))
                         for loc, traces in self.iteritems())

    def add(self, loc, trace):
        assert isinstance(loc, str) and loc, loc
        assert isinstance(trace, Trace), trace

        if loc not in self:
            self[loc] = Traces()

        not_in = trace not in self[loc]
        if not_in:
            self[loc].add(trace)
        return not_in

    def merge(self, new_traces):
        """
        add new traces and return those that are really new
        """
        new_traces_ = DTraces()
        for loc in new_traces:
            for trace in new_traces[loc]:
                not_in = self.add(loc, trace)
                if not_in:
                    new_traces_.add(loc, trace)
                else:
                    mlog.warn("trace {} exist".format(trace))
        return new_traces_

    @staticmethod
    def parse(trace_str, inv_decls):
        """
        parse trace for new traces

        trace_str = ['vtrace1: 0 285 1 9 285 9 ',
        'vtrace1: 0 285 2 18 285 9 ',
        'vtrace1: 0 285 4 36 285 9 ']
        """
        assert isinstance(inv_decls, data.miscs.DSymbs)\
            and inv_decls, inv_decls

        lines = [l.strip() for l in trace_str]
        lines = [l for l in lines if l]

        dtraces = DTraces()
        for l in lines:
            # 22: 8460 16 0 1 16 8460
            parts = l.split(':')
            assert len(parts) == 2, parts
            loc, tracevals = parts[0], parts[1]
            loc = loc.strip()  # 22
            ss = inv_decls[loc].names
            vs = tracevals.strip().split()
            mytrace = Trace.parse(ss, vs)
            dtraces.add(loc, mytrace)
        return dtraces

    def vwrite(self, inv_decls, tracefile):
        """
        write traces to file
        each loc will have its own file

        file 'traces_loc.csv'
        var1, var2, var3
        v1, v2, v2
        ...
        """
        assert inv_decls and isinstance(
            inv_decls, data.miscs.DSymbs), inv_decls
        assert tracefile and isinstance(tracefile, str), tracefile

        ss = []
        for loc in self:
            traces = [inv_decls[loc]]
            traces.extend([', '.join(map(str, t.vs)) for t in self[loc]])
            traces = ['{}: {}'.format(loc, t) for t in traces]
            ss.extend(traces)

        CM.vwrite(tracefile, '\n'.join(ss))

    @classmethod
    def vread(cls, tracefile):
        assert tracefile and isinstance(tracefile, str), tracefile

        trace_str = []
        # determine variable declarations for different locations
        inv_decls = data.miscs.DSymbs()
        for line in CM.iread_strip(tracefile):
            loc, contents = line.split(':')
            if loc not in inv_decls:
                inv_decls[loc] = data.miscs.Symbs.mk(contents)  # I x, I y
            else:
                trace_str.append(line.replace(',', ''))

        dtraces = DTraces.parse(trace_str, inv_decls)
        return inv_decls, dtraces


class Inp(SymbsVals):
    pass


class Inps(SymbsValsSet):
    def merge(self, ds, ss):
        """
        ds can be
        1. cexs = {loc:{inv: {'x': val, 'y': val}}}
        2. [cexs]
        3. [inp]
        """

        if not ds:
            return Inps()

        def f(d):
            inps = []
            for loc in d:
                for inv in d[loc]:
                    for d_ in d[loc][inv]:
                        inp = tuple(d_[s] for s in ss)
                        inps.append(inp)
            return inps

        if (isinstance(ds, list) and all(isinstance(d, dict) for d in ds)):
            newInps = [inp for d in ds for inp in f(d)]

        elif isinstance(ds, dict):
            newInps = f(ds)

        else:
            assert isinstance(ds, set) and\
                all(isinstance(d, tuple) for d in ds), ds
            newInps = [inp for inp in ds]

        newInps = [Inp(ss, inp) for inp in newInps]
        newInps = set(inp for inp in newInps if inp not in self)
        for inp in newInps:
            self.add(inp)
        return Inps(newInps)
