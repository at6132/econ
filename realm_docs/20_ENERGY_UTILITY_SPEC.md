# Energy & utility grid (Phase 2.5)

Electricity is **not** a tradeable material. Power is a **regional service** measured in **watt-hours (Wh)**.

## Rules

- Production recipes draw **`energy_wh`** per batch from the **grid** or an on-plot **battery**.
- Generators export **`grid_export_wh`** into the regional pool (no `electricity` inventory).
- **Batteries** (`battery_bank` blueprint) are the only building that stores energy off-grid.
- **Warehouses / yard bulk** never hold electrons.
- **Bazaar / P2P** cannot list or buy electricity.
- **Frontier Grid & Power Co.** (`frontier_grid_co`) is the default utility; players receive a **monthly usage statement** (game-day 30 cadence).

## Law 4 amendment

Delivered power is a billed service on regional grids. **Fuel** (coal, etc.) remains tradeable matter. **Stored energy** only in batteries.

## Constants

- `WH_PER_LEGACY_ELEC_UNIT = 1000` (1 legacy inventory unit = 1 kWh)
- Grid capacity on generators: kWh per game-day per blueprint rating
