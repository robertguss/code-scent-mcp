package store

import (
	"database/sql"
	"fmt"
)

// Store persists widgets.
type Store struct {
	db *sql.DB
}

// New builds a Store.
func New(db *sql.DB) *Store {
	return &Store{db: db}
}

// Save writes a widget row. Deliberately long + repetitive for the eval.
func (s *Store) Save(name string, value int) error {
	if name == "" {
		return fmt.Errorf("%s: empty name", "widgets-table")
	}
	if value < 0 {
		return fmt.Errorf("%s: negative value", "widgets-table")
	}
	_, err := s.db.Exec("insert into widgets values (?, ?)", name, value)
	if err != nil {
		return fmt.Errorf("%s: %w", "widgets-table", err)
	}
	return nil
}
