//! Public erased-Row controls for the pinned local libsql wrapper.
use libsql::{Builder, Connection, Error, Row, Value, ValueType};
use std::panic::{catch_unwind, AssertUnwindSafe};

async fn connection() -> Connection {
    Builder::new_local(":memory:")
        .build()
        .await
        .unwrap()
        .connect()
        .unwrap()
}

async fn row(conn: &Connection, sql: &str) -> Row {
    let mut rows = conn.query(sql, ()).await.unwrap();
    rows.next().await.unwrap().unwrap()
}

fn invalid_type<T: std::fmt::Debug>(value: libsql::Result<T>) {
    assert!(matches!(value, Err(Error::InvalidColumnType)), "{value:?}");
}

#[tokio::test]
async fn public_row_preserves_all_text_bytes_and_owned_lifetime() {
    let conn = connection().await;
    for text in ["a\0b", "\0start", "end\0", "\0a\0\0b\0", "é\0世界🙂", ""] {
        let mut rows = conn
            .query("SELECT ?1, typeof(?1), hex(?1)", [Value::Text(text.into())])
            .await
            .unwrap();
        let current: Row = rows.next().await.unwrap().unwrap();
        assert_eq!(current.get::<String>(1).unwrap(), "text");
        let hex: String = text
            .as_bytes()
            .iter()
            .map(|byte| format!("{byte:02X}"))
            .collect();
        assert_eq!(current.get::<String>(2).unwrap(), hex);
        assert_eq!(current.get_str(0).unwrap().as_bytes(), text.as_bytes());
        assert_eq!(
            current.get::<String>(0).unwrap().as_bytes(),
            text.as_bytes()
        );
        let owned = current.get_value(0).unwrap();
        drop(current);
        drop(rows);
        assert_eq!(owned, Value::Text(text.into()));
    }
}

#[tokio::test]
async fn public_row_rejects_invalid_utf8_without_panic_and_recovers() {
    let conn = connection().await;
    // Invalid bytes precede and follow NUL; SQLite must retain each byte first.
    for hex in ["80", "800061", "610080", "F09F0061", "6100C0AF"] {
        let current = row(&conn, &format!("SELECT CAST(x'{hex}' AS TEXT), typeof(CAST(x'{hex}' AS TEXT)), hex(CAST(x'{hex}' AS TEXT))")).await;
        assert_eq!(current.get::<String>(1).unwrap(), "text");
        assert_eq!(current.get::<String>(2).unwrap(), hex);
        invalid_type(
            catch_unwind(AssertUnwindSafe(|| current.get_value(0))).expect("get_value panicked"),
        );
        invalid_type(
            catch_unwind(AssertUnwindSafe(|| current.get::<String>(0)))
                .expect("get String panicked"),
        );
        invalid_type(
            catch_unwind(AssertUnwindSafe(|| current.get_str(0))).expect("get_str panicked"),
        );
        drop(current);
        assert_eq!(
            row(&conn, "SELECT 'recovered'").await.get_str(0).unwrap(),
            "recovered"
        );
    }
}

#[tokio::test]
async fn public_row_keeps_storage_types_and_rejects_nontext_strings() {
    let conn = connection().await;
    let current = row(&conn, "SELECT NULL, '', x'', x'0080FF0061', 42, 1.5").await;
    let values = [
        Value::Null,
        Value::Text(String::new()),
        Value::Blob(vec![]),
        Value::Blob(vec![0, 128, 255, 0, 97]),
        Value::Integer(42),
        Value::Real(1.5),
    ];
    let types = [
        ValueType::Null,
        ValueType::Text,
        ValueType::Blob,
        ValueType::Blob,
        ValueType::Integer,
        ValueType::Real,
    ];
    for (index, (value, kind)) in values.iter().zip(types).enumerate() {
        let index = index as i32;
        assert_eq!(
            std::mem::discriminant(&current.column_type(index).unwrap()),
            std::mem::discriminant(&kind),
        );
        assert_eq!(&current.get_value(index).unwrap(), value);
        if index == 1 {
            assert_eq!(current.get_str(index).unwrap(), "");
        } else {
            invalid_type(current.get_str(index));
        }
    }
    assert_eq!(current.get::<Vec<u8>>(3).unwrap(), [0, 128, 255, 0, 97]);
    assert_eq!(current.get::<i64>(4).unwrap(), 42);
    assert_eq!(current.get::<f64>(5).unwrap(), 1.5);
}

#[tokio::test]
async fn public_row_and_rows_reject_out_of_range_indices_and_recover() {
    let conn = connection().await;
    let mut rows = conn.query("SELECT 'text', 42", ()).await.unwrap();
    let current = rows.next().await.unwrap().unwrap();
    for index in [-1, i32::MIN, 2, i32::MAX] {
        assert!(matches!(
            current.get_value(index),
            Err(Error::InvalidColumnIndex)
        ));
        assert!(matches!(
            current.get::<String>(index),
            Err(Error::InvalidColumnIndex)
        ));
        assert!(matches!(
            current.get_str(index),
            Err(Error::InvalidColumnIndex)
        ));
        assert!(matches!(
            current.column_type(index),
            Err(Error::InvalidColumnIndex)
        ));
        assert!(matches!(
            rows.column_type(index),
            Err(Error::InvalidColumnIndex)
        ));
        assert_eq!(current.column_name(index), None);
        assert_eq!(rows.column_name(index), None);
    }
    assert_eq!(current.get_str(0).unwrap(), "text");
    assert_eq!(current.column_name(0), Some("'text'"));
    assert_eq!(rows.column_name(0), Some("'text'"));
    assert!(matches!(rows.column_type(0).unwrap(), ValueType::Text));
    drop(current);
    drop(rows);
    assert_eq!(row(&conn, "SELECT 7").await.get::<i64>(0).unwrap(), 7);
}

#[tokio::test]
async fn public_statement_columns_keep_borrowed_metadata() {
    let conn = connection().await;
    let statement = conn
        .prepare("SELECT 7 AS number, 'text' AS label")
        .await
        .unwrap();
    let columns = statement.columns();
    assert_eq!(columns.len(), 2);
    assert_eq!(columns[0].name(), "number");
    assert_eq!(columns[1].name(), "label");
}
