package cache

import (
	"context"
	"log"
	"time"

	"github.com/valkey-io/valkey-go"
)

var (
	valkeyClient valkey.Client
	timeCached = 24
)

func Connect(url string) valkey.Client {
	if valkeyClient != nil {
		return valkeyClient
	}
	client, err := valkey.NewClient(valkey.ClientOption{
		InitAddress: []string{url},
	})

	if err != nil {
		log.Fatal("[VALKEY] Ha habido un error conectando a la base de datos:", err)
	}
	valkeyClient = client

	defer client.Close()

	return client
}

func Get(key string) string {
	if valkeyClient == nil {
		log.Fatal("[VALKEY] No se ha establecido una conexión con la base de datos")
	}
	val, err := valkeyClient.Do(context.Background(), valkeyClient.B().Getex().Key(key).Build()).ToString()
	if err != nil {
		log.Fatal("[VALKEY] Ha habido un error al hacer Get", err)
	}
	return val
}

func Set(key string, value string) {
	if valkeyClient == nil {
		log.Fatal("[VALKEY] No se ha establecido una conexión con la base de datos")
	}
	err := valkeyClient.Do(context.Background(), valkeyClient.B().Set().Key(key).Value(value).Ex(time.Duration(timeCached)*time.Hour).Build()).Error()
	if err != nil {
		log.Fatal("[VALKEY] Ha habido un error al settear", err)
	}
}