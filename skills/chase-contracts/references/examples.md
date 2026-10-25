# Examples

The results below are the ones returned by CHASE with nuXmv.

## Arbiter: refinement and counterexample

```json
{"name": "Spec", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
 "assumptions": ["G F !req"], "guarantees": ["G (req -> F grant)"]}

{"name": "Impl", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
 "guarantees": ["G (req -> X grant)"]}

{"name": "Lazy", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
 "guarantees": ["G (req -> X X grant) | G !grant"]}
```

- `refines(Impl, Spec)` is `valid`: granting in the next step is a way of
  granting eventually.
- `refines(Lazy, Spec)` is `invalid`, with `failed: "guarantees"` and the
  trace

  ```
  0: req=True,  grant=False
  1: req=False, grant=False  <- loop starts
  ```

  The request at step 0 is never granted: the second disjunct `G !grant`
  allows a component that never grants. Fix: drop `| G !grant`.

## Pipeline: composition, assumptions, quotient

A sensor raises an alarm when it sees an obstacle; a brake stops the car
after an alarm, if alarms do not last forever.

```json
{"name": "Sensor", "inputs": {"obstacle": "bool"}, "outputs": {"alarm": "bool"},
 "guarantees": ["G (obstacle -> alarm)"]}

{"name": "Brake", "inputs": {"alarm": "bool"}, "outputs": {"stop": "bool"},
 "assumptions": ["G F !alarm"], "guarantees": ["G (alarm -> X stop)"]}

{"name": "Car", "inputs": {"obstacle": "bool"}, "outputs": {"stop": "bool"},
 "assumptions": ["G F !obstacle"], "guarantees": ["G (obstacle -> X stop)"]}
```

1. `compose([Sensor, Brake])` connects the two contracts through `alarm`.
2. `refines(composite, Car)` is `invalid` with `failed: "assumptions"`:

   ```
   0: obstacle=True,  alarm=True, stop=False
   1: obstacle=False, alarm=True, stop=False  <- loop starts
   ```

   The environment of `Car` is respected (the obstacle goes away), but the
   sensor may keep the alarm on forever, which breaks the assumption of the
   brake.
3. Fix the sensor guarantee to `G (alarm <-> obstacle)`. The refinement is
   now `valid`, and `compatible` on the composite is `sat` (the result is not
   vacuous).
4. `quotient(Car, Sensor)` gives the contract of the missing component, with
   input `alarm` (from the sensor), input `obstacle`, and output `stop`.
   Composing it with the sensor refines `Car`, and `Brake` refines it: the
   brake is a valid implementation of the missing component.

## Python

```python
import chase_cps as cc
from chase_cps import Contract

sensor = Contract.from_dict({...})
brake = Contract.from_dict({...})
car = Contract.from_dict({...})

r = cc.refines(sensor.compose(brake), car)
print(r.status, r.failed)
print(r.assumptions.trace)

missing = car.quotient(sensor, name="Missing")
print(missing)
print(cc.refines(brake, missing).status)
```
