from riftbound.core.cards import UnitCard
from riftbound.core.enums import Domain
from riftbound.core.player import Player


def test_channel_generates_energy_and_power():
    player = Player(name="A")
    player.add_rune(Domain.FURY)
    player.add_rune(Domain.CALM)

    player.channel()

    assert player.energy == 2
    assert player.power_pool[Domain.CALM] == 1
    assert player.power_pool[Domain.FURY] == 1

    card = UnitCard(name="Disciple", cost_energy=1, cost_power=Domain.FURY, might=2)
    assert player.can_pay_cost(card.cost_energy, card.cost_power)
    assert player.pay_cost(card.cost_energy, card.cost_power)
    assert player.energy == 1
    assert Domain.FURY not in player.power_pool


def test_cannot_pay_missing_power():
    player = Player(name="B")
    player.add_rune(Domain.CALM)
    player.add_rune(Domain.CALM)
    player.channel()

    assert not player.can_pay_cost(1, Domain.FURY)