package cache

import "testing"

func TestGet(t *testing.T) {
	c := &Cache{values: map[string]int{"a": 1}}
	if Get(c, "a") != 1 {
		t.Fatal("want 1")
	}
}
