import test from 'node:test';
import assert from 'node:assert/strict';
import {number} from '../src/format.ts';

test('large monetary decimal strings remain exact',()=>assert.equal(number('12345678901234567890.1250',2),'12,345,678,901,234,567,890.13'));
test('NAV rounding and carry do not use floats',()=>{assert.equal(number('1.2344500000',4),'1.2345');assert.equal(number('9.99995',4),'10.0000');});
test('negative values and unknown values are distinct',()=>{assert.equal(number('-0.12445',4),'-0.1245');assert.equal(number(null),'—');assert.equal(number('0'),'0.0000');});
