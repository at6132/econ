"""Contracts — supply, forward, loan, equity, tender, service.

A contract is a multi-step enforceable agreement between two parties (or
a party and the system). Each contract type has its own state machine and
its own escrow / breach rules.

Submodules:
  * ``realm.contracts.social``    — Supply contracts and social interactions
  * ``realm.contracts.stubs``     — Phase-2 stubs for forward / loan / equity / service
                                    (formerly ``realm.contract_stubs``)
  * ``realm.contracts.forward``   — Forward contract delivery (formerly ``realm.genesis_forwards``)
  * ``realm.contracts.tenders``   — Government / system tenders

Phase 5 will add a dedicated ``loans.py`` module here when bank-loan logic
is extracted from ``realm.genesis.bank``.
"""
