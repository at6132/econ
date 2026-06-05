"""Deal-making — bilateral contracts, market tactics, and genesis bank loans."""

from realm.deals.bank_loans import (
    BankLoan,
    GENESIS_BANK_PARTY_ID,
    GENESIS_BANK_STARTING_CASH_CENTS,
    request_loan,
    seed_genesis_bank,
    tick_loan_repayment,
)
from realm.deals.bilateral_contracts import (
    BilateralContract,
    propose_bilateral_contract,
    tick_bilateral_contracts,
    tick_contract_proposals,
)
from realm.deals.market_tactics import tick_market_cornering, tick_predatory_pricing
from realm.deals.market_warfare import (
    tick_cartel_formation,
    tick_panic_selling,
    tick_short_positions,
    tick_speculative_positions,
)

__all__ = [
    "BankLoan",
    "BilateralContract",
    "GENESIS_BANK_PARTY_ID",
    "GENESIS_BANK_STARTING_CASH_CENTS",
    "propose_bilateral_contract",
    "request_loan",
    "seed_genesis_bank",
    "tick_bilateral_contracts",
    "tick_contract_proposals",
    "tick_loan_repayment",
    "tick_market_cornering",
    "tick_predatory_pricing",
    "tick_cartel_formation",
    "tick_panic_selling",
    "tick_speculative_positions",
    "tick_short_positions",
]
