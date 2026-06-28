package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: app <name>")
		return
	}
	fmt.Println("hello", os.Args[1])
}
