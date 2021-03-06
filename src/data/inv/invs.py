from time import time
import pdb
from collections import Counter

import z3

import settings
from helpers.miscs import Miscs, Z3
import helpers.vcommon as CM

import data.inv.base
import data.inv.eqt
import data.inv.oct
import data.inv.mp
import data.inv.prepost

DBG = pdb.set_trace
mlog = CM.getLogger(__name__, settings.logger_level)


class Invs(set):
    def __init__(self, invs=set()):
        assert all(isinstance(inv, data.inv.base.Inv) for inv in invs), invs
        super().__init__(invs)

    def __str__(self, print_stat=False, delim='\n'):
        invs = sorted(self, reverse=True,
                      key=lambda inv: isinstance(inv, data.inv.eqt.Eqt))
        return delim.join(inv.__str__(print_stat) for inv in invs)

    def __contains__(self, inv):
        assert isinstance(inv, data.inv.base.Inv), inv
        return super().__contains__(inv)

    @property
    def typ_ctr(self):
        return Counter(inv.__class__.__name__ for inv in self)

    # PUBLIC
    def add(self, inv):
        assert isinstance(inv, data.inv.base.Inv), inv

        not_in = inv not in self
        if not_in:
            super().add(inv)
        return not_in

    def test(self, traces):
        # assert isinstance(traces, Traces)
        assert(self), self

        def f(tasks):
            return [(inv, inv.test(traces)) for inv in tasks]
        wrs = Miscs.run_mp("test", list(self), f)

        myinvs = set()
        for inv, passed in wrs:
            if passed:
                myinvs.add(inv)
            else:
                mlog.debug("remove {}".format(inv))

        invs = self.__class__(myinvs)
        return invs

    def simplify(self, use_reals):
        assert isinstance(use_reals, bool), use_reals

        eqts, eqts_largecoefs, octs, mps, preposts, falseinvs = \
            self.classify(self)

        assert not falseinvs, falseinvs
        non_mps = eqts + preposts + octs

        if non_mps and len(mps) >= 2:  # parallelizing simplifying mps
            non_mps_exprs = [e.expr(use_reals) for e in non_mps]
            conj = z3.And(non_mps_exprs)

            def f(mps):
                return [mp for mp in mps
                        if not Z3._imply(conj, mp.expr(use_reals))]
            wrs = Miscs.run_mp("simplifying {} mps".format(len(mps)), mps, f)

            mps = [mp for mp in wrs]

        rs = non_mps + mps
        if rs:
            is_conj = True
            rs = self._simplify(rs, is_conj, use_reals)

        return self.__class__(rs + eqts_largecoefs)

    @classmethod
    def classify(cls, invs):
        eqts, eqts_largecoefs, octs, mps, preposts, falseinvs = [], [], [], [], [], []

        for inv in invs:
            if isinstance(inv, data.inv.eqt.Eqt):
                if len(Miscs.get_coefs(inv.inv)) > 10:
                    eqts_largecoefs.append(inv)
                else:
                    eqts.append(inv)
            elif isinstance(inv, data.inv.oct.Oct):
                octs.append(inv)
            elif isinstance(inv, data.inv.mp.MP):
                mps.append(inv)
            elif isinstance(inv, data.inv.prepost.PrePost):
                preposts.append(inv)
            else:
                assert isinstance(inv, data.inv.invs.FalseInv), inv
                falseinvs.append(inv)
        return eqts, eqts_largecoefs, octs, mps, preposts, falseinvs

    # PRIVATE
    @classmethod
    def _simplify(cls, invs, is_conj, use_reals):
        assert invs, invs

        st = time()
        eqts, eqts_largecoefs, octs, mps, preposts, falseinvs = \
            cls.classify(invs)

        def mysorted(ps):
            return sorted(ps, key=lambda p: len(Miscs.get_vars(p.inv)))
        eqts = mysorted(eqts+eqts_largecoefs)
        octs = mysorted(octs)
        mps = mysorted(mps)

        myinvs = eqts + falseinvs + preposts + octs + mps
        myinvs_exprs = [inv.expr(use_reals) for inv in myinvs]

        def _imply(js, i):
            iexpr = myinvs_exprs[i]
            # don't consider/remove equality
            if iexpr.decl().kind() == z3.Z3_OP_EQ:
                ret = False
            else:
                jexprs = [myinvs_exprs[j] for j in js]
                ret = Z3._imply(jexprs, iexpr, is_conj)
            # if ret:
            #     print '{} => {}'.format(jexprs, iexpr)
            return ret

        results = Miscs.simplify_idxs(list(range(len(myinvs))), _imply)
        results = [myinvs[i] for i in results]

        Miscs.show_removed('_simplify', len(invs), len(results), time() - st)
        return results


class DInvs(dict):
    """
    {loc -> Invs}, Invs is a set
    """

    def __setitem__(self, loc, invs):
        assert isinstance(loc, str) and loc, loc
        assert isinstance(invs, Invs), invs

        super().__setitem__(loc, invs)

    @property
    def invs(self):
        return (inv for invs in self.values() for inv in invs)

    @property
    def siz(self): return sum(map(len, self.values()))

    @property
    def typ_ctr(self):
        return sum([self[loc].typ_ctr for loc in self], Counter())

    @property
    def n_eqs(self):
        return self.typ_ctr[data.inv.eqt.Eqt.__name__]

    def __str__(self, print_stat=False, print_first_n=None):
        ss = []

        for loc in sorted(self):
            eqts, eqts_largecoefs, octs, mps, preposts, falseinvs = \
                self[loc].classify(self[loc])
            ss.append("{} ({} invs):".format(loc, len(self[loc])))

            invs = sorted(eqts + eqts_largecoefs, reverse=True, key=str) + \
                sorted(preposts, reverse=True, key=str) + \
                sorted(octs, reverse=True, key=str) + \
                sorted(mps, reverse=True, key=str) +\
                sorted(falseinvs, reverse=True, key=str)

            if print_first_n and print_first_n < len(invs):
                invs = invs[:print_first_n] + ['...']

            ss.extend("{}. {}".format(
                i+1,
                inv if isinstance(inv, str) else inv.__str__(print_stat))
                for i, inv in enumerate(invs))

        return '\n'.join(ss)

    def add(self, loc, inv):
        assert isinstance(loc, str) and loc, loc
        assert isinstance(inv, data.inv.base.Inv), inv

        return self.setdefault(loc, Invs()).add(inv)

    def merge(self, dinvs):
        assert isinstance(dinvs, DInvs), dinvs
        for loc in dinvs:
            for inv in dinvs[loc]:
                if not inv.is_disproved:
                    self.add(loc, inv)

    def remove_disproved(self):
        dinvs = self.__class__()
        for loc in self:
            for inv in self[loc]:
                if not inv.is_disproved:
                    dinvs.add(loc, inv)
        return dinvs

    def test(self, dtraces):
        # assert isinstance(dtraces, DTraces)
        assert self.siz, self

        st = time()
        tasks = [loc for loc in self if self[loc]]

        def f(tasks):
            return [(loc, self[loc].test(dtraces[loc])) for loc in tasks]

        wrs = Miscs.run_mp("test_dinvs", tasks, f)
        dinvs = DInvs([(loc, invs) for loc, invs in wrs if invs])
        Miscs.show_removed("test_dinvs", self.siz, dinvs.siz, time() - st)
        return dinvs

    def update(self, dinvs):
        assert isinstance(dinvs, DInvs), dinvs
        deltas = self.__class__()
        for loc in self:
            if loc not in dinvs:
                dinvs[loc] = self[loc]
                deltas[loc] = self[loc]
            elif dinvs[loc] != self[loc]:
                new_invs = Invs()
                for inv in self[loc]:
                    if inv not in dinvs[loc]:
                        new_invs.add(inv)
                    else:
                        invs_l = list(dinvs[loc])
                        old_inv = invs_l[invs_l.index(inv)]
                        if inv.stat != old_inv.stat:
                            inv.stat = old_inv.stat
                dinvs[loc] = self[loc]
                deltas[loc] = new_invs

        return deltas

    def simplify(self, use_reals):
        assert isinstance(use_reals, bool), use_reals
        assert(self.siz), self

        st = time()

        def f(tasks):
            return [(loc, self[loc].simplify(use_reals)) for loc in tasks]
        wrs = Miscs.run_mp('simplify', list(self), f)

        dinvs = self.__class__((loc, invs) for loc, invs in wrs if invs)
        Miscs.show_removed('simplify', self.siz, dinvs.siz, time() - st)
        return dinvs

    @classmethod
    def mk_false_invs(cls, locs):
        dinvs = cls()
        for loc in locs:
            dinvs.add(loc, FalseInv.mk())
        return dinvs

    @classmethod
    def mk(cls, loc, invs):
        assert isinstance(invs, Invs), invs
        new_invs = cls()
        new_invs[loc] = invs
        return new_invs


class FalseInv(data.inv.base.Inv):
    """
    Use
    """

    def __init__(self, inv, stat=None):
        assert inv == 0, inv
        super().__init__(inv, stat)

    def __str__(self, print_stat=False):
        s = str(self.inv)
        if print_stat:
            s = "{} {}".format(s, self.stat)
        return s

    def expr(self, _):
        return z3.BoolVal(False)

    @classmethod
    def mk(cls):
        return FalseInv(0)
