package com.mycom.myapp.repository;

import com.mycom.myapp.entity.NoteCollection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface NoteCollectionRepository extends JpaRepository<NoteCollection, Long> {
}
