import assert from 'node:assert/strict';
import {test} from 'node:test';
import {advance, numericAttribute} from '../webcam_mapper/static/avatar-motion.mjs';

test('SVG parser preserves cubic commands, signed coordinates and exponents', () => {
  const parsed = numericAttribute('M -1.2,3e-2 C 4,5 6,7 8,9 Z');
  assert.deepEqual(parsed.values, [-1.2, .03, 4, 5, 6, 7, 8, 9]);
  assert.equal(parsed.parts.join('#'), 'M #,# C #,# #,# #,# Z');
});

test('interpolation is independent of display frame rate and never overshoots', () => {
  let at30 = 0, at120 = 0;
  for (let i = 0; i < 30; i++) at30 = advance(at30, 1, 1000 / 30, 80);
  for (let i = 0; i < 120; i++) at120 = advance(at120, 1, 1000 / 120, 80);
  assert.ok(Math.abs(at30 - at120) < 1e-12);
  assert.ok(at30 > .99 && at30 < 1);
  assert.equal(advance(.4, 1, 16, 0), 1);
  const retargeted = advance(.4, 0, 16, 80);
  assert.ok(retargeted > 0 && retargeted < .4);
});
