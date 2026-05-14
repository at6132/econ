from realm.core.ids import MaterialId, PartyId
from realm.core.inventory import Inventory


def test_matter_transfer_conserves_total_units() -> None:
    inv = Inventory()
    alice = PartyId("alice")
    bob = PartyId("bob")
    m = MaterialId("timber")
    assert inv.add(alice, m, 100).ok is True
    total = inv.total_units()
    assert inv.transfer(material=m, qty=30, from_party=alice, to_party=bob).ok is True
    assert inv.total_units() == total
    assert inv.qty(alice, m) == 70
    assert inv.qty(bob, m) == 30
