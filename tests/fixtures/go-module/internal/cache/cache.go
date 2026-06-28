package cache

// Cache is a tiny in-memory map.
type Cache struct {
	values map[string]int
}

// Get returns a cached value.
func Get(c *Cache, key string) int {
	return c.values[key]
}
