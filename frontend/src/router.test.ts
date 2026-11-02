import { expect, test } from 'vitest'
import { addSourcesHref, parseHash } from './router'

test.each([
  ['', '/'],
  ['#', '/'],
  ['#/', '/'],
  ['#/brain', '/brain'],
  ['#/sources/new?client=abc', '/sources/new'],
])('parseHash(%j) has path %j', (hash, path) => {
  expect(parseHash(hash).path).toBe(path)
})

test('parseHash reads the query after the path', () => {
  const { query } = parseHash('#/sources/new?client=abc&x=1')

  expect(query.get('client')).toBe('abc')
  expect(query.get('x')).toBe('1')
})

test('parseHash gives an empty query when there is none', () => {
  expect(parseHash('#/brain').query.toString()).toBe('')
})

test('addSourcesHref links to a new intake without a client', () => {
  expect(addSourcesHref()).toBe('#/sources/new')
})

test('addSourcesHref puts the client in the link', () => {
  expect(addSourcesHref('a b')).toBe('#/sources/new?client=a%20b')
  expect(parseHash(addSourcesHref('a b')).query.get('client')).toBe('a b')
})
